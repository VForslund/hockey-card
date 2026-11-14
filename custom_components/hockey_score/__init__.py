"""The Hockey Score integration: polls a hockey-api instance and serves
the two bundled dashboard cards (www/hockey-score-cards.js)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import HockeyApiClient
from .const import CONF_API_KEY, CONF_URL, DOMAIN
from .coordinator import HockeyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

_COMPONENT_DIR = Path(__file__).parent
# The cards ship inside the integration: it serves the JS itself
# (frontend.add_extra_js_url, the browser_mod pattern), so dashboards need
# no Lovelace resource entries and card updates ride along with
# integration updates.
_CARDS_URL_PATH = "/hockey_score_cards"
_CARDS_DONE = "hockey_score_cards_served"


@dataclass
class RuntimeData:
    client: HockeyApiClient
    coordinator: HockeyCoordinator


async def _async_serve_cards(hass: HomeAssistant) -> None:
    """Serve www/ as a static path once per HA run and register it as an
    extra JS module, versioned with the manifest version for cache
    busting. Entry reloads (the Marketplace update primitive) re-run
    setup: the guard turns those into a no-op."""
    if hass.data.get(_CARDS_DONE):
        return
    # Attempted once per HA run — no retry storms on instances that
    # can't serve cards at all.
    hass.data[_CARDS_DONE] = True
    # Imported lazily: the integration loads even without the frontend
    # set up.
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    try:
        # Version from the loader's in-memory integration object — never a
        # disk read (HA's loop detector hard-errors those over time); the
        # integration is always loaded by the time an entry is set up.
        integration = await async_get_integration(hass, DOMAIN)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARDS_URL_PATH, str(_COMPONENT_DIR / "www"), True)]
        )
        add_extra_js_url(
            hass,
            f"{_CARDS_URL_PATH}/hockey-score-cards.js?v={integration.version}",
        )
    except Exception:
        # Cards are optional: on an http-less/frontend-less HA there are
        # no cards, but sensors, polling and events must still come up.
        _LOGGER.exception("not serving the bundled dashboard cards on this instance")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry (URL + key from the config flow)."""
    await _async_serve_cards(hass)
    session = async_get_clientsession(hass)
    client = HockeyApiClient(
        session, entry.data[CONF_URL], entry.data[CONF_API_KEY]
    )
    coordinator = HockeyCoordinator(hass, entry, client)
    # First refresh happens now; every later refresh follows the cadence
    # the API data itself dictates (2 s live / 60 s idle).
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = RuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
