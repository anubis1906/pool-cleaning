"""Constants for the Pool Cleaning Reports integration."""
from __future__ import annotations

DOMAIN = "pool_cleaning"

CONF_SENDER = "sender"
CONF_FOLDER = "folder"
CONF_MARK_SEEN = "mark_seen"
CONF_USE_SSL = "use_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_MARK_SEEN = True
DEFAULT_USE_SSL = True
DEFAULT_SCAN_INTERVAL = 60  # minutes

SERVICE_REFRESH = "refresh"

# Known chemical-reading labels we specifically look for so they get a sensible
# unit/icon. Any other label found in the "CHEMICAL READINGS" section of the
# email is still turned into a sensor, just without one of these hints.
READING_HINTS: dict[str, dict[str, str]] = {
    "chlorine": {"unit": "ppm", "icon": "mdi:flask"},
    "salt": {"unit": "ppm", "icon": "mdi:shaker-outline"},
    "ph": {"unit": None, "icon": "mdi:ph"},
    "alkalinity": {"unit": "ppm", "icon": "mdi:flask-outline"},
    "cyanuric_acid": {"unit": "ppm", "icon": "mdi:flask-outline"},
    "calcium_hardness": {"unit": "ppm", "icon": "mdi:flask-outline"},
    "bromine": {"unit": "ppm", "icon": "mdi:flask"},
    "phosphates": {"unit": "ppb", "icon": "mdi:flask-outline"},
    "temperature": {"unit": "°F", "icon": "mdi:thermometer"},
}

ATTR_TECHNICIAN = "technician"
ATTR_CUSTOMER_NAME = "customer_name"
ATTR_ADDRESS = "address"
ATTR_WARNING = "warning_text"
ATTR_CHEMICALS = "chemicals_added"
ATTR_AREA = "area"
