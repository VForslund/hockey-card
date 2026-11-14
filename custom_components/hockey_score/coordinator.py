"""The polling coordinator: cadence + the continuity engine + event firing."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import continuity, polling
from .api import HockeyApiClient, HockeyApiError

_LOGGER = logging.getLogger(__name__)


class HockeyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches /team on a live-aware cadence and runs the event engine.

    The dynamic interval works because DataUpdateCoordinator re-reads
    ``update_interval`` when it schedules the refresh after each cycle:
    2 s while live, 60 s while idle. /team/static is fetched on fixture
    rollover or every 15 minutes, decided by the pure polling module.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: HockeyApiClient
    ) -> None:
        # config_entry is passed explicitly: the framework wires the
        # coordinator's shutdown to the entry (unload, reload after key
        # rotation, restartless Marketplace-style updates) and honors the
        # "disable polling" toggle. Without it we'd depend on HA's implicit
        # current-entry fallback, which core is removing.
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="hockey_score",
            update_interval=timedelta(seconds=polling.IDLE_POLL_SECONDS),
        )
        self._client = client
        self._engine = continuity.initial_state()
        self._static: dict[str, Any] | None = None
        self._static_fetched_at: float | None = None
        self._prev_badge_key: tuple | None = None
        self._standings: dict[str, Any] | None = None
        self._standings_fetched_at: float | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            team = await self._client.async_get_team()
        except HockeyApiError as err:
            # Every event type follows the same continuity rule: a failed
            # poll breaks the chain; the next success re-baselines silently.
            self._engine = continuity.on_poll_failure(self._engine)
            raise UpdateFailed(str(err)) from err

        # Badges: refetch on fixture rollover, else every 15 minutes. A
        # static failure never blocks game data or mutes events.
        cur_badge_key = polling.badge_key(team)
        if polling.should_fetch_static(
            self._prev_badge_key,
            cur_badge_key,
            self._static_fetched_at,
            time.monotonic(),
        ):
            try:
                self._static = await self._client.async_get_static()
            except HockeyApiError as err:
                _LOGGER.debug("static/badges fetch failed: %s", err)
            # Record the ATTEMPT, success or not: a failing /team/static
            # must fall back to the 15-min TTL instead of being retried on
            # every /team poll (every 2 s while live).
            self._static_fetched_at = time.monotonic()
            self._prev_badge_key = cur_badge_key

        # Standings: hourly TTL, non-fatal (a failure never blocks game data
        # or mutes events), attempt-stamped like the badge fetch.
        if polling.should_fetch_standings(
            self._standings_fetched_at, time.monotonic()
        ):
            try:
                self._standings = await self._client.async_get_standings()
            except HockeyApiError as err:
                _LOGGER.debug("standings fetch failed: %s", err)
            self._standings_fetched_at = time.monotonic()

        self.update_interval = timedelta(
            seconds=polling.next_interval_seconds(bool(team.get("is_live")))
        )

        events, self._engine = continuity.on_poll_success(self._engine, team)
        for event_type, payload in events:
            self.hass.bus.async_fire(event_type, payload)

        return {"team": team, "static": self._static, "standings": self._standings}
