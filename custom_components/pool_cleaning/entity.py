"""Shared device-info helpers for Pool Cleaning Reports entities."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def main_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Pool Service",
        manufacturer="Pool Cleaning Reports",
        model="Weekly service report",
    )


def area_device_info(entry: ConfigEntry, area: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{area.lower()}")},
        name=area,
        manufacturer="Pool Cleaning Reports",
        model="Weekly service report",
        via_device=(DOMAIN, entry.entry_id),
    )
