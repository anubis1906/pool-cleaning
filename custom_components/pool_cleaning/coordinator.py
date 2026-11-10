"""DataUpdateCoordinator that polls IMAP for the latest pool-service report."""
from __future__ import annotations

import email
import imaplib
import logging
from datetime import timedelta
from email.message import Message

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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


class PoolCleaningCoordinator(DataUpdateCoordinator[ServiceReport]):
    """Polls the mailbox and keeps the latest parsed report.

    Every poll re-fetches and re-parses whichever matching email currently
    has the highest IMAP UID, rather than only acting on mail newer than a
    remembered UID. That keeps this restart-proof: the mailbox itself is
    the single source of truth, so there's nothing to lose when the
    coordinator (and its in-memory data) is recreated on a Home Assistant
    restart. Re-parsing the same email weekly is negligible cost.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )

    async def _async_update_data(self) -> ServiceReport:
        try:
            html = await self.hass.async_add_executor_job(self._fetch_latest_email)
        except (imaplib.IMAP4.error, OSError) as err:
            raise UpdateFailed(f"Error communicating with IMAP server: {err}") from err

        if html is None:
            # No matching email found at all; keep showing whatever we had.
            return self.data if self.data is not None else ServiceReport()

        try:
            return parse_report_email(html)
        except Exception as err:  # noqa: BLE001 - one odd email shouldn't take every entity offline
            _LOGGER.exception("Failed to parse the latest pool-service report email")
            if self.data is not None:
                return self.data
            raise UpdateFailed(f"Failed to parse report email: {err}") from err

    def _fetch_latest_email(self) -> str | None:
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
            if not uids:
                return None
            latest_uid = max(uids)

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
                return None

            if mark_seen:
                conn.uid("store", str(latest_uid), "+FLAGS", "\\Seen")

            return html
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
