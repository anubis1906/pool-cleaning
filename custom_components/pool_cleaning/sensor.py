"""Sensor entities for Pool Cleaning Reports."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ADDRESS,
    ATTR_CUSTOMER_NAME,
    ATTR_WARNING,
    DOMAIN,
    READING_HINTS,
)
from .coordinator import PoolCleaningCoordinator
from .entity import area_device_info, main_device_info
from .parser import ServiceReport


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCleaningCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        LastServiceSensor(coordinator, entry),
        TechnicianSensor(coordinator, entry),
        SafeToSwimSensor(coordinator, entry),
    ]

    added_reading_keys: set[tuple[str, str]] = set()
    added_area_summaries: set[str] = set()

    for area, area_report in coordinator.data.areas.items():
        for key in area_report.readings:
            entities.append(ReadingSensor(coordinator, entry, area, key))
            added_reading_keys.add((area, key))
        entities.append(ChemicalsAddedSensor(coordinator, entry, area))
        added_area_summaries.add(area)

    async_add_entities(entities)

    @callback
    def _add_new_entities() -> None:
        report: ServiceReport = coordinator.data
        new_entities: list[SensorEntity] = []
        for area, area_report in report.areas.items():
            for key in area_report.readings:
                if (area, key) not in added_reading_keys:
                    new_entities.append(ReadingSensor(coordinator, entry, area, key))
                    added_reading_keys.add((area, key))
            if area not in added_area_summaries:
                new_entities.append(ChemicalsAddedSensor(coordinator, entry, area))
                added_area_summaries.add(area)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class _BaseSensor(CoordinatorEntity[PoolCleaningCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PoolCleaningCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry


class LastServiceSensor(_BaseSensor):
    _attr_name = "Last Service"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: PoolCleaningCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_service"
        self._attr_device_info = main_device_info(entry)

    @property
    def native_value(self):
        report: ServiceReport = self.coordinator.data
        visit = report.visit_datetime
        if visit is None:
            return None
        return dt_util.as_local(visit)

    @property
    def extra_state_attributes(self) -> dict:
        report: ServiceReport = self.coordinator.data
        return {
            ATTR_CUSTOMER_NAME: report.customer_name,
            ATTR_ADDRESS: report.address,
            ATTR_WARNING: report.warning_text,
        }


class TechnicianSensor(_BaseSensor):
    _attr_name = "Technician"
    _attr_icon = "mdi:account-hard-hat"

    def __init__(self, coordinator: PoolCleaningCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_technician"
        self._attr_device_info = main_device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.data.technician


class SafeToSwimSensor(_BaseSensor):
    _attr_name = "Safe to Swim After"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:pool"

    def __init__(self, coordinator: PoolCleaningCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_safe_to_swim_after"
        self._attr_device_info = main_device_info(entry)

    @property
    def native_value(self):
        when = self.coordinator.data.safe_to_swim_after
        if when is None:
            return None
        return dt_util.as_local(when)


class ReadingSensor(_BaseSensor):
    """A single chemical reading (chlorine, pH, salt, ...) for one area."""

    def __init__(
        self,
        coordinator: PoolCleaningCoordinator,
        entry: ConfigEntry,
        area: str,
        key: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._area = area
        self._key = key
        hint = READING_HINTS.get(key, {})
        label = self._current_reading_label() or key.replace("_", " ").title()
        self._attr_name = label
        self._attr_icon = hint.get("icon", "mdi:test-tube")
        self._attr_native_unit_of_measurement = hint.get("unit")
        self._attr_unique_id = f"{entry.entry_id}_{area.lower()}_{key}"
        self._attr_device_info = area_device_info(entry, area)

    def _current_reading_label(self) -> str | None:
        area_report = self.coordinator.data.areas.get(self._area)
        if area_report is None:
            return None
        reading = area_report.readings.get(self._key)
        return reading.label if reading else None

    @property
    def native_value(self):
        area_report = self.coordinator.data.areas.get(self._area)
        if area_report is None:
            return None
        reading = area_report.readings.get(self._key)
        if reading is None:
            return None
        return reading.value


class ChemicalsAddedSensor(_BaseSensor):
    """Summary of chemicals added to one area during the latest visit."""

    _attr_icon = "mdi:beaker-plus-outline"

    def __init__(
        self, coordinator: PoolCleaningCoordinator, entry: ConfigEntry, area: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._area = area
        self._attr_name = "Chemicals Added"
        self._attr_unique_id = f"{entry.entry_id}_{area.lower()}_chemicals_added"
        self._attr_device_info = area_device_info(entry, area)

    @property
    def native_value(self):
        area_report = self.coordinator.data.areas.get(self._area)
        if area_report is None:
            return 0
        return len(area_report.chemicals_added)

    @property
    def extra_state_attributes(self) -> dict:
        area_report = self.coordinator.data.areas.get(self._area)
        if area_report is None:
            return {}
        return {
            chem.label: f"{chem.value} {chem.unit}" if chem.unit else chem.value
            for chem in area_report.chemicals_added.values()
        }
