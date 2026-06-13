"""Skywatch sensor platform.

11 core sensors backed by the coordinator's data dict, plus one per
watch-list entry. Sensors that ship a row-list attribute (recent,
overhead, military, movements, search) are marked
EntityCategory.DIAGNOSTIC — they're not surfaced in user-facing
dashboards by default, and we ship a `recorder.exclude` snippet in the
README to keep the history DB lean.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._device import build_device_info
from .classify import WatchEntry
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SkywatchCoordinator


@dataclass(frozen=True, kw_only=True)
class SkywatchSensorDescription(SensorEntityDescription):
    """SensorEntityDescription extended with value + attribute extractors."""

    value_fn: Callable[[dict], Any] = lambda _data: None
    attributes_fn: Callable[[dict], dict | None] | None = None


def _attrs_excluding_count(data: dict, key: str) -> dict | None:
    section = data.get(key)
    if not isinstance(section, dict):
        return None
    return {k: v for k, v in section.items() if k != "count"}


SENSORS: tuple[SkywatchSensorDescription, ...] = (
    SkywatchSensorDescription(
        key="log_today",
        translation_key="log_today",
        name="Sightings today",
        icon="mdi:calendar-today",
        value_fn=lambda d: d.get("today", {}).get("count", 0),
    ),
    SkywatchSensorDescription(
        key="log_this_week",
        translation_key="log_this_week",
        name="Sightings this week",
        icon="mdi:calendar-week",
        value_fn=lambda d: d.get("stats", {}).get("this_week", 0),
    ),
    SkywatchSensorDescription(
        key="log_recent",
        translation_key="log_recent",
        name="Recent sightings",
        icon="mdi:database",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("recent", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "recent"),
    ),
    SkywatchSensorDescription(
        key="log_search",
        translation_key="log_search",
        name="Search results",
        icon="mdi:magnify",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("search", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "search"),
    ),
    SkywatchSensorDescription(
        key="log_stats",
        translation_key="log_stats",
        name="Sightings all-time",
        icon="mdi:chart-bar",
        value_fn=lambda d: d.get("stats", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "stats"),
    ),
    SkywatchSensorDescription(
        key="log_top_routes",
        translation_key="log_top_routes",
        name="Top routes",
        icon="mdi:airplane-takeoff",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("top_routes", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "top_routes"),
    ),
    SkywatchSensorDescription(
        key="log_overhead",
        translation_key="log_overhead",
        name="Overhead sightings",
        icon="mdi:airplane",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("overhead", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "overhead"),
    ),
    SkywatchSensorDescription(
        key="log_hour_histogram",
        translation_key="log_hour_histogram",
        name="Sightings hour-of-day",
        icon="mdi:clock-time-eight-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("hour_histogram", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "hour_histogram"),
    ),
    SkywatchSensorDescription(
        key="military_sightings",
        translation_key="military_sightings",
        name="Military sightings",
        icon="mdi:airplane-shield",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("military", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "military"),
    ),
    SkywatchSensorDescription(
        key="movements_today",
        translation_key="movements_today",
        name="Airport movements today",
        icon="mdi:airport",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("movements_today", {}).get("count", 0),
        attributes_fn=lambda d: _attrs_excluding_count(d, "movements_today"),
    ),
    SkywatchSensorDescription(
        key="flights_in_area",
        translation_key="flights_in_area",
        name="Aircraft in area",
        icon="mdi:radar",
        value_fn=lambda _d: None,  # Source.current_flights() — see SkywatchFlightsSensor
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SkywatchCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for desc in SENSORS:
        if desc.key == "flights_in_area":
            entities.append(SkywatchFlightsInAreaSensor(coordinator, desc))
        else:
            entities.append(SkywatchSensor(coordinator, desc))
    entities.extend(SkywatchWatchSensor(coordinator, watch) for watch in coordinator.watch_list)
    async_add_entities(entities)


class SkywatchSensor(CoordinatorEntity, SensorEntity):
    """Sensor whose value + attributes come from the coordinator data dict."""

    entity_description: SkywatchSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SkywatchCoordinator,
        description: SkywatchSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attributes_fn is None:
            return None
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return self.entity_description.attributes_fn(data)


class SkywatchFlightsInAreaSensor(CoordinatorEntity, SensorEntity):
    """Live count of flights inside the watch radius (not from DB).

    Reads `Source.current_flights()` so it reflects the live source
    snapshot rather than the persisted DB. For FR24 this proxies the
    `sensor.flightradar24_current_in_area` attribute count.
    """

    entity_description: SkywatchSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SkywatchCoordinator,
        description: SkywatchSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.source.current_flights())


class SkywatchWatchSensor(CoordinatorEntity, SensorEntity):
    """One sensor per watch-list entry.

    State is the lifetime count of sightings that matched the watch
    (by registration or by FR24 privacy-block fingerprint). The
    attributes carry the last-seen details for templates / cards.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:airplane-marker"
    _attr_translation_key = "watch"

    def __init__(self, coordinator: SkywatchCoordinator, watch: WatchEntry) -> None:
        super().__init__(coordinator)
        self._watch = watch
        entry = coordinator.config_entry  # type: ignore[union-attr]
        self._attr_unique_id = f"{entry.entry_id}_watch_{watch.slug}"
        self._attr_name = watch.label
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> int:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return 0
        return data.get("watches", {}).get(self._watch.slug, {}).get("count", 0)

    @property
    def extra_state_attributes(self) -> dict | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        section = data.get("watches", {}).get(self._watch.slug)
        if not isinstance(section, dict):
            return None
        return {k: v for k, v in section.items() if k != "count"}
