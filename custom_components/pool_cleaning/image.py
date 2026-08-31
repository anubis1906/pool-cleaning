"""Before/after photo entities for Pool Cleaning Reports."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import PoolCleaningCoordinator
from .entity import area_device_info
from .parser import ServiceReport


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCleaningCoordinator = hass.data[DOMAIN][entry.entry_id]

    added: set[tuple[str, str]] = set()
    initial: list[ReportPhotoEntity] = []
    for area, area_report in coordinator.data.areas.items():
        for slot, url in (("before", area_report.photo_before), ("after", area_report.photo_after)):
            if url:
                initial.append(ReportPhotoEntity(hass, coordinator, entry, area, slot))
                added.add((area, slot))
    async_add_entities(initial)

    @callback
    def _add_new_entities() -> None:
        report: ServiceReport = coordinator.data
        new_entities: list[ReportPhotoEntity] = []
        for area, area_report in report.areas.items():
            for slot, url in (
                ("before", area_report.photo_before),
                ("after", area_report.photo_after),
            ):
                if url and (area, slot) not in added:
                    new_entities.append(ReportPhotoEntity(hass, coordinator, entry, area, slot))
                    added.add((area, slot))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class ReportPhotoEntity(CoordinatorEntity[PoolCleaningCoordinator], ImageEntity):
    """Shows the most recent before/after photo for one area."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PoolCleaningCoordinator,
        entry: ConfigEntry,
        area: str,
        slot: str,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._area = area
        self._slot = slot
        self._attr_name = f"{slot.title()} Photo"
        self._attr_unique_id = f"{entry.entry_id}_{area.lower()}_{slot}_photo"
        self._attr_device_info = area_device_info(entry, area)
        self._attr_image_last_updated = dt_util.utcnow()

    def _current_url(self) -> str | None:
        area_report = self.coordinator.data.areas.get(self._area)
        if area_report is None:
            return None
        return area_report.photo_before if self._slot == "before" else area_report.photo_after

    @property
    def image_url(self) -> str | None:
        return self._current_url()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_image_last_updated = dt_util.utcnow()
        self._cached_image = None
        super()._handle_coordinator_update()
