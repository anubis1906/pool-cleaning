"""Parse the weekly pool-service HTML report email into structured data.

The report layout is a templated field-service email (job header, then one
block per body of water such as "POOL" or "SPA", each with a "CHEMICAL
READINGS" section and a "CHEMICALS ADDED" section, plus before/after photos).

We don't rely on exact HTML tag structure, since that can vary between
providers/templates. Instead we walk the rendered text in document order and
use a small state machine to recognise section headers and label/value/unit
triples. This is more resilient to markup changes than CSS-selector based
scraping, at the cost of being a little heuristic - see README for how to
tune it if your provider's template doesn't parse cleanly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from datetime import date, datetime, time

from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_AREA_HEADERS = {"POOL", "SPA", "HOT TUB", "FOUNTAIN"}
_SECTION_HEADERS = {"CHEMICAL READINGS", "CHEMICALS ADDED"}
_IGNORE_TOKENS = {"BEFORE", "AFTER", "JOB FEEDBACK"}
_MAX_LABEL_TOKENS = 5

_JOB_DATE_RE = re.compile(r"Job Date:\s*([\d/]+)", re.IGNORECASE)
_ARRIVAL_RE = re.compile(r"Arrival:\s*([\d:]+\s*[AP]M)", re.IGNORECASE)
_TECHNICIAN_RE = re.compile(r"Technician:\s*", re.IGNORECASE)
_WAIT_HOURS_RE = re.compile(r"wait at least (\d+(?:\.\d+)?)\s*hours?", re.IGNORECASE)


def slugify(text: str) -> str:
    """Turn a label like 'Enzymes/Phos Free' into 'enzymes_phos_free'."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


@dataclass
class ChemicalValue:
    label: str
    value: float
    unit: str | None


@dataclass
class AreaReport:
    readings: dict[str, ChemicalValue] = field(default_factory=dict)
    chemicals_added: dict[str, ChemicalValue] = field(default_factory=dict)
    photo_before: str | None = None
    photo_after: str | None = None


@dataclass
class ServiceReport:
    customer_name: str | None = None
    address: str | None = None
    job_date: date | None = None
    arrival_time: time | None = None
    technician: str | None = None
    warning_text: str | None = None
    wait_hours: float | None = None
    areas: dict[str, AreaReport] = field(default_factory=dict)

    @property
    def visit_datetime(self) -> datetime | None:
        if self.job_date is None:
            return None
        if self.arrival_time is None:
            return datetime.combine(self.job_date, time(0, 0))
        return datetime.combine(self.job_date, self.arrival_time)

    @property
    def safe_to_swim_after(self) -> datetime | None:
        visit = self.visit_datetime
        if visit is None or self.wait_hours is None:
            return None
        from datetime import timedelta

        return visit + timedelta(hours=self.wait_hours)


def _leaf_tokens(soup: BeautifulSoup) -> list[str]:
    """Return stripped, non-empty text nodes in document order."""
    tokens: list[str] = []
    for node in soup.find_all(string=True):
        parent = node.parent.name if node.parent else ""
        if parent in ("script", "style"):
            continue
        text = node.strip()
        if text:
            tokens.append(text)
    return tokens


def _parse_label_value_sections(tokens: list[str]) -> dict[str, dict[str, ChemicalValue]]:
    """Walk tokens once, grouping them into per-area readings/chemicals-added
    dicts. Recognises "LABEL VALUE [UNIT]" triples within each section."""
    result: dict[str, dict[str, ChemicalValue]] = {}
    current_area: str | None = None
    current_section: str | None = None
    pending_label: list[str] = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]
        upper = tok.upper()

        if upper in _AREA_HEADERS:
            current_area = upper.title()
            current_section = None
            pending_label = []
            i += 1
            continue

        if upper in _SECTION_HEADERS:
            current_section = "readings" if upper == "CHEMICAL READINGS" else "chemicals_added"
            pending_label = []
            i += 1
            continue

        if upper in _IGNORE_TOKENS:
            pending_label = []
            i += 1
            continue

        if current_area is None or current_section is None:
            i += 1
            continue

        if _NUMBER_RE.match(tok) and pending_label:
            label = " ".join(pending_label).strip().rstrip(":")
            pending_label = []
            key = slugify(label)

            unit = None
            if i + 1 < n:
                nxt = tokens[i + 1]
                nxt_upper = nxt.upper()
                if (
                    not _NUMBER_RE.match(nxt)
                    and nxt_upper not in _AREA_HEADERS
                    and nxt_upper not in _SECTION_HEADERS
                    and nxt_upper not in _IGNORE_TOKENS
                    and len(nxt) <= 20
                ):
                    unit = nxt
                    i += 1

            result.setdefault(current_area, {}).setdefault(current_section, {})
            result[current_area][current_section][key] = ChemicalValue(
                label=label, value=float(tok), unit=unit
            )
            i += 1
            continue

        pending_label.append(tok)
        if len(pending_label) > _MAX_LABEL_TOKENS:
            pending_label.pop(0)
        i += 1

    return result


def _find_customer_and_address(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    address = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "maps.google" in href or "maps.apple" in href or "goo.gl/maps" in href:
            address = a.get_text(" ", strip=True)
            break
    if address is None:
        # Fall back: any link whose text looks like a street address.
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if re.search(r"\d+.+,\s*[A-Za-z]+,?\s*[A-Z]{2}\s*\d{5}", text):
                address = text
                break

    customer_name = None
    if address is not None:
        # Look for the nearest preceding bold/strong text within the same container.
        container = None
        for a in soup.find_all("a", href=True):
            if a.get_text(" ", strip=True) == address:
                container = a.parent
                break
        if container is not None:
            texts = [t.strip() for t in container.find_all(string=True) if t.strip()]
            if texts and texts[0] != address:
                customer_name = texts[0]
    return customer_name, address


def _find_warning_text(soup: BeautifulSoup) -> str | None:
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    match = re.search(r"[^.]*wait at least \d+(?:\.\d+)?\s*hours?[^.]*\.", text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None


def _find_photos(soup: BeautifulSoup, areas: dict[str, AreaReport]) -> None:
    """Best-effort: associate <img> tags with the nearest area and a
    before/after label found in surrounding text."""
    if not areas:
        return
    area_names = list(areas.keys())
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        # Walk up to find the nearest ancestor that also contains an area
        # header, and the nearest before/after label near the image.
        label = None
        area_name = area_names[-1]
        node = img
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            text = node.get_text(" ", strip=True).upper()
            if label is None:
                if "AFTER" in text:
                    label = "after"
                elif "BEFORE" in text:
                    label = "before"
            for area in area_names:
                if area.upper() in text:
                    area_name = area
                    break
        if label is None:
            label = "after"
        area_report = areas[area_name]
        if label == "before" and area_report.photo_before is None:
            area_report.photo_before = src
        elif area_report.photo_after is None:
            area_report.photo_after = src


def parse_report_email(html: str) -> ServiceReport:
    """Parse the raw HTML body of a pool-service report email."""
    soup = BeautifulSoup(html, "html.parser")
    tokens = _leaf_tokens(soup)
    full_text = soup.get_text("\n", strip=True)

    report = ServiceReport()

    if (m := _JOB_DATE_RE.search(full_text)) is not None:
        try:
            report.job_date = datetime.strptime(m.group(1), "%m/%d/%y").date()
        except ValueError:
            try:
                report.job_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
            except ValueError:
                _LOGGER.debug("Could not parse job date %s", m.group(1))

    if (m := _ARRIVAL_RE.search(full_text)) is not None:
        try:
            report.arrival_time = datetime.strptime(
                m.group(1).strip(), "%I:%M %p"
            ).time()
        except ValueError:
            _LOGGER.debug("Could not parse arrival time %s", m.group(1))

    if (m := _TECHNICIAN_RE.search(full_text)) is not None:
        rest = full_text[m.end():].strip()
        report.technician = rest.split("\n", 1)[0].strip()

    report.warning_text = _find_warning_text(soup)
    if report.warning_text and (m := _WAIT_HOURS_RE.search(report.warning_text)):
        report.wait_hours = float(m.group(1))

    report.customer_name, report.address = _find_customer_and_address(soup)

    parsed = _parse_label_value_sections(tokens)

    for area_name, sections in parsed.items():
        area_report = AreaReport(
            readings=sections.get("readings", {}),
            chemicals_added=sections.get("chemicals_added", {}),
        )
        report.areas[area_name] = area_report

    _find_photos(soup, report.areas)

    if not report.areas:
        _LOGGER.debug(
            "No pool/spa areas found while parsing report email; raw tokens: %s",
            tokens,
        )

    return report
