"""Sensor platform: sensor.hockey_team + sensor.hockey_team_badges +
sensor.hockey_team_standings.

Entity ids stay identical to the rest-sensor era (MARKETPLACE_PLAN.md §4):
the names "Hockey Team" / "Hockey Team Badges" slug to exactly the ids the
dashboard and automations already use. Attributes are produced by the
pure flatten module — the same code the unit tests lock down.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import flatten
from .coordinator import HockeyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            HockeyTeamSensor(coordinator, entry.entry_id),
            HockeyBadgesSensor(coordinator, entry.entry_id),
            HockeyStandingsSensor(coordinator, entry.entry_id),
        ]
    )


class HockeyTeamSensor(CoordinatorEntity[HockeyCoordinator], SensorEntity):
    """The game sensor: state Live/Idle, flat attributes."""

    def __init__(self, coordinator: HockeyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        # No device_info, deliberately: a device would prefix the entity
        # id with the device name and break the sensor.hockey_team
        # contract (MARKETPLACE_PLAN.md §4). These stay loose entities,
        # exactly like the rest-sensor era.
        self._attr_name = "Hockey Team"
        self._attr_unique_id = f"{entry_id}_team"

    @property
    def native_value(self) -> str:
        team = (self.coordinator.data or {}).get("team") or {}
        return "Live" if team.get("is_live") else "Idle"

    @property
    def icon(self) -> str:
        team = (self.coordinator.data or {}).get("team") or {}
        return "mdi:hockey-puck" if team.get("is_live") else "mdi:calendar-clock"

    @property
    def extra_state_attributes(self) -> dict:
        return flatten.flatten_team((self.coordinator.data or {}).get("team") or {})


class HockeyBadgesSensor(CoordinatorEntity[HockeyCoordinator], SensorEntity):
    """The badge sensor: state team name, badge attributes."""

    def __init__(self, coordinator: HockeyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        # No device_info — same entity-id contract as HockeyTeamSensor.
        self._attr_name = "Hockey Team Badges"
        self._attr_unique_id = f"{entry_id}_badges"
        self._attr_icon = "mdi:hockey-sticks"

    @property
    def native_value(self) -> str:
        static = (self.coordinator.data or {}).get("static") or {}
        return static.get("team_name", "")

    @property
    def extra_state_attributes(self) -> dict:
        static = (self.coordinator.data or {}).get("static") or {}
        return flatten.flatten_static(static)


class HockeyStandingsSensor(CoordinatorEntity[HockeyCoordinator], SensorEntity):
    """The league table sensor: state = tracked team's position, full table
    in attributes (sensor.hockey_team_standings)."""

    def __init__(self, coordinator: HockeyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        # No device_info — same entity-id contract as HockeyTeamSensor.
        self._attr_name = "Hockey Team Standings"
        self._attr_unique_id = f"{entry_id}_standings"
        self._attr_icon = "mdi:format-list-numbered"

    @property
    def native_value(self) -> int | None:
        standings = (self.coordinator.data or {}).get("standings") or {}
        return standings.get("tracked_position")

    @property
    def extra_state_attributes(self) -> dict:
        standings = (self.coordinator.data or {}).get("standings") or {}
        return flatten.flatten_standings(standings)
