"""Config flow: URL + API key, validated live against the API.

No prefill of any real host (MARKETPLACE_PLAN.md §8.3) and no secret ever
leaves the config entry. The options flow re-opens both fields so keys can
be rotated without deleting the entry.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    HockeyApiClient,
    HockeyApiAuthError,
    HockeyApiError,
    normalize_url,
)
from .const import CONF_API_KEY, CONF_URL, DOMAIN


def _schema(url: str | None = None, api_key: str | None = None) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_URL, description={"suggested_value": url or ""}): str,
            vol.Required(
                CONF_API_KEY,
                description={"suggested_value": api_key or "", "mode": "password"},
            ): str,
        }
    )


class HockeyScoreConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of a Hockey Score instance."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> HockeyScoreOptionsFlowHandler:
        # The framework calls this with the entry and injects it onto the
        # returned flow instance (self.config_entry) — nothing to pass on.
        return HockeyScoreOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """The single setup step friends see."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            if not errors:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                try:
                    session = async_get_clientsession(self.hass)
                    client = HockeyApiClient(session, url, user_input[CONF_API_KEY])
                    team = await client.async_validate_credentials()
                except HockeyApiAuthError:
                    errors["base"] = "invalid_auth"
                except HockeyApiError:
                    # connection/time-out errors are subclasses of this
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"Hockey Score — {team.get('team_name') or 'hockey'}",
                        data={
                            CONF_URL: url,
                            CONF_API_KEY: user_input[CONF_API_KEY],
                        },
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(),
            errors=errors,
        )


class HockeyScoreOptionsFlowHandler(OptionsFlow):
    """Let the user change URL/key (e.g. after key rotation)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self.config_entry
        old_url = entry.data.get(CONF_URL, "")
        old_key = entry.data.get(CONF_API_KEY, "")
        if user_input is not None:
            try:
                url = normalize_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            if not errors:
                try:
                    session = async_get_clientsession(self.hass)
                    client = HockeyApiClient(session, url, user_input[CONF_API_KEY])
                    await client.async_validate_credentials()
                except HockeyApiAuthError:
                    errors["base"] = "invalid_auth"
                except HockeyApiError:
                    errors["base"] = "cannot_connect"
                else:
                    changed = self.hass.config_entries.async_update_entry(
                        entry,
                        data={CONF_URL: url, CONF_API_KEY: user_input[CONF_API_KEY]},
                    )
                    if changed:
                        # Credentials live in the running client, not just in
                        # storage — reload the entry so a new coordinator is
                        # built with the new URL/key (core's own pattern for
                        # credential changes; entry reload, not HA restart).
                        self.hass.config_entries.async_schedule_reload(
                            entry.entry_id
                        )
                    return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(old_url, old_key),
            errors=errors,
        )
