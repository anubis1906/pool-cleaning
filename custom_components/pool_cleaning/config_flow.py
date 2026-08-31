"""Config flow for Pool Cleaning Reports."""
from __future__ import annotations

import imaplib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_FOLDER,
    CONF_MARK_SEEN,
    CONF_SCAN_INTERVAL,
    CONF_SENDER,
    CONF_USE_SSL,
    DEFAULT_FOLDER,
    DEFAULT_MARK_SEEN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_SSL,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,
        vol.Optional(CONF_SENDER, default=""): str,
        vol.Optional(CONF_USE_SSL, default=DEFAULT_USE_SSL): bool,
        vol.Optional(CONF_MARK_SEEN, default=DEFAULT_MARK_SEEN): bool,
    }
)


def _test_connection(data: dict[str, Any]) -> None:
    """Blocking IMAP login check, run in the executor."""
    conn_cls = imaplib.IMAP4_SSL if data.get(CONF_USE_SSL, True) else imaplib.IMAP4
    conn = conn_cls(data[CONF_HOST], data[CONF_PORT])
    try:
        conn.login(data[CONF_USERNAME], data[CONF_PASSWORD])
        conn.select(data.get(CONF_FOLDER, DEFAULT_FOLDER))
    finally:
        try:
            conn.close()
        except imaplib.IMAP4.error:
            pass
        conn.logout()


class PoolCleaningConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pool Cleaning Reports."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            sender = user_input.get(CONF_SENDER, "").strip()
            user_input[CONF_SENDER] = sender or None

            try:
                await self.hass.async_add_executor_job(_test_connection, user_input)
            except imaplib.IMAP4.error:
                errors["base"] = "invalid_auth"
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                title = f"Pool Reports ({user_input[CONF_USERNAME]})"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PoolCleaningOptionsFlow:
        return PoolCleaningOptionsFlow(config_entry)


class PoolCleaningOptionsFlow(config_entries.OptionsFlow):
    """Handle options: scan interval and mark-as-read behaviour."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): int,
                vol.Optional(
                    CONF_MARK_SEEN,
                    default=options.get(
                        CONF_MARK_SEEN,
                        self.config_entry.data.get(CONF_MARK_SEEN, DEFAULT_MARK_SEEN),
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
