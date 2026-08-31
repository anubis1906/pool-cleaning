"""DataUpdateCoordinator that polls IMAP for new pool-service report emails."""
from __future__ import annotations

import email
import imaplib
import logging
from datetime import timedelta
from email.message import Message

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_FOLDER,
    CONF_MARK_SEEN,
    CONF_SCAN_INTERVAL,
    CONF_SENDER,
    CONF_USE_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .parser import ServiceReport, parse_report_email

_LOGGER = logging.getLogger(__name__)
_STORAGE_VERSION = 1


class PoolCleaningCoordinator(DataUpdateCoordinator[ServiceReport]):
    """Polls the mailbox and keeps the latest parsed report."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._store: Store = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_last_uid"
        )
        self._last_uid = 0
        self._last_uid_loaded = False
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )

    async def _async_load_last_uid(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._last_uid = stored.get("last_uid", 0)
        self._last_uid_loaded = True

    async def _async_save_last_uid(self) -> None:
        await self._store.async_save({"last_uid": self._last_uid})

    async def _async_update_data(self) -> ServiceReport:
        if not self._last_uid_loaded:
            await self._async_load_last_uid()

        try:
            result = await self.hass.async_add_executor_job(self._fetch_latest_email)
        except (imaplib.IMAP4.error, OSError) as err:
            raise UpdateFailed(f"Error communicating with IMAP server: {err}") from err

        if result is None:
            # No new email since the last check; keep showing the previous data.
            if self.data is not None:
                return self.data
            return ServiceReport()

        uid, html = result
        report = parse_report_email(html)
        self._last_uid = uid
        await self._async_save_last_uid()
        return report

    def _fetch_latest_email(self) -> tuple[int, str] | None:
        """Blocking IMAP fetch, run in the executor."""
        data = self.entry.data
        host = data["host"]
        port = data["port"]
        username = data["username"]
        password = data["password"]
        folder = data.get(CONF_FOLDER, "INBOX")
        sender = data.get(CONF_SENDER)
        use_ssl = data.get(CONF_USE_SSL, True)
        mark_seen = self.entry.options.get(CONF_MARK_SEEN, data.get(CONF_MARK_SEEN, True))

        conn = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        try:
            conn.login(username, password)
            conn.select(folder)

            criteria = f'(FROM "{sender}")' if sender else "ALL"
            typ, search_data = conn.uid("search", None, criteria)
            if typ != "OK" or not search_data or not search_data[0]:
                return None

            uids = [int(u) for u in search_data[0].split()]
            new_uids = [u for u in uids if u > self._last_uid]
            if not new_uids:
                return None

            latest_uid = max(new_uids)
            typ, msg_data = conn.uid("fetch", str(latest_uid), "(RFC822)")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                return None

            raw = msg_data[0][1]
            message = email.message_from_bytes(raw)
            html = _extract_html(message)
            if html is None:
                _LOGGER.warning(
                    "Latest matching email (uid %s) had no HTML body to parse",
                    latest_uid,
                )
                self._last_uid = latest_uid
                return None

            if mark_seen:
                conn.uid("store", str(latest_uid), "+FLAGS", "\\Seen")

            return latest_uid, html
        finally:
            try:
                conn.close()
            except imaplib.IMAP4.error:
                pass
            conn.logout()


def _extract_html(message: Message) -> str | None:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/html":
                return _decode_part(part)
        return None
    if message.get_content_type() == "text/html":
        return _decode_part(message)
    return None


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")
