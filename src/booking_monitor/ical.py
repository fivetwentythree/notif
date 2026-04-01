from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
import time
from typing import Any

import httpx
from icalendar import Calendar

from booking_monitor.config import PropertyConfig
from booking_monitor.models import FeedCheckpoint, NormalizedBooking, utc_now_iso


USER_AGENT = "booking-monitor/0.1.0"


@dataclass(slots=True)
class CalendarFetchResult:
    kind: str
    observed_at: str
    text: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    body_hash: str | None = None
    error: str | None = None


class CalendarClient:
    def __init__(self, timeout_seconds: int, retries: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = max(1, retries)

    def fetch(self, property_config: PropertyConfig, checkpoint: FeedCheckpoint) -> CalendarFetchResult:
        headers = {"User-Agent": USER_AGENT}
        if checkpoint.etag:
            headers["If-None-Match"] = checkpoint.etag
        if checkpoint.last_modified:
            headers["If-Modified-Since"] = checkpoint.last_modified

        last_error: str | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = httpx.get(
                    property_config.calendar_url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=self.timeout_seconds,
                )
                observed_at = utc_now_iso()

                if response.status_code == 304:
                    return CalendarFetchResult(
                        kind="not_modified",
                        observed_at=observed_at,
                        etag=response.headers.get("ETag") or checkpoint.etag,
                        last_modified=response.headers.get("Last-Modified") or checkpoint.last_modified,
                    )

                response.raise_for_status()
                body_hash = sha256(response.content).hexdigest()
                return CalendarFetchResult(
                    kind="modified",
                    observed_at=observed_at,
                    text=response.text,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    body_hash=body_hash,
                )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 5))

        return CalendarFetchResult(kind="failed", observed_at=utc_now_iso(), error=last_error)


def parse_calendar(property_config: PropertyConfig, raw_calendar: str) -> list[NormalizedBooking]:
    calendar = Calendar.from_ical(raw_calendar)
    deduped: dict[str, NormalizedBooking] = {}

    for component in calendar.walk("VEVENT"):
        uid = _normalize_text(component.get("UID"))
        if not uid:
            continue

        recurrence_id = _normalize_temporal_value(_component_value(component, "RECURRENCE-ID"))[0] or None
        start, all_day = _normalize_temporal_value(_component_value(component, "DTSTART"))
        end, _ = _normalize_temporal_value(_component_value(component, "DTEND"))

        booking = NormalizedBooking(
            property_id=property_config.id,
            property_name=property_config.name,
            uid=uid,
            recurrence_id=recurrence_id,
            start=start,
            end=end,
            all_day=all_day,
            summary=_normalize_text(component.get("SUMMARY")),
            description=_normalize_text(component.get("DESCRIPTION")),
            status=(_normalize_text(component.get("STATUS")) or "CONFIRMED").upper(),
            sequence=_coerce_int(component.get("SEQUENCE")),
            last_modified=(
                _normalize_temporal_value(_component_value(component, "LAST-MODIFIED"))[0]
                or _normalize_temporal_value(_component_value(component, "DTSTAMP"))[0]
            ),
            source=property_config.source,
        )
        existing = deduped.get(booking.booking_key)
        if existing is None or _is_newer_version(booking, existing):
            deduped[booking.booking_key] = booking

    return sorted(deduped.values(), key=lambda item: (item.start, item.end, item.booking_key))


def _component_value(component: Any, key: str) -> Any | None:
    field = component.get(key)
    if field is None:
        return None
    return getattr(field, "dt", field)


def _normalize_temporal_value(value: Any | None) -> tuple[str, bool]:
    if value is None:
        return "", False
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat(), False
    if isinstance(value, date):
        return value.isoformat(), True
    return str(value), False


def _normalize_text(value: Any | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _coerce_int(value: Any | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _version_rank(booking: NormalizedBooking) -> tuple[int, str]:
    return (booking.sequence or 0, booking.last_modified or "")


def _is_newer_version(candidate: NormalizedBooking, existing: NormalizedBooking) -> bool:
    return _version_rank(candidate) >= _version_rank(existing)
