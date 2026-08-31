"""Binary sensors for Pool Cleaning Reports."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import PoolCleaningCoordinator
from .entity import main_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCleaningCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ChemicalsAddedWarningSensor(coordinator, entry)])


class ChemicalsAddedWarningSensor(
    CoordinatorEntity[PoolCleaningCoordinator], BinarySensorEntity
):
    """On when the latest report includes a wait-before-swimming warning."""

    _attr_has_entity_name = True
    _attr_name = "Wait Before Swimming"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: PoolCleaningCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_wait_before_swimming"
        self._attr_device_info = main_device_info(entry)

    @property
    def is_on(self) -> bool:
        report = self.coordinator.data
        if not report.warning_text:
            return False
        deadline = report.safe_to_swim_after
        if deadline is None:
            return True
        if deadline.tzinfo is None:
            deadline = dt_util.as_local(deadline)
        return dt_util.utcnow() < deadline.astimezone(dt_util.UTC)

    @property
    def extra_state_attributes(self) -> dict:
        return {"warning_text": self.coordinator.data.warning_text}
