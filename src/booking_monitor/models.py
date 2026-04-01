from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any


SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class ChangeKind(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class NormalizedBooking:
    property_id: str
    property_name: str
    uid: str
    recurrence_id: str | None
    start: str
    end: str
    all_day: bool
    summary: str | None
    description: str | None
    status: str
    sequence: int | None
    last_modified: str | None
    source: str | None = None

    @property
    def booking_key(self) -> str:
        recurrence_token = self.recurrence_id or "base"
        return f"{self.property_id}:{self.uid}:{recurrence_token}"

    @property
    def fingerprint(self) -> str:
        payload = {
            "start": self.start,
            "end": self.end,
            "all_day": self.all_day,
            "summary": self.summary,
            "description": self.description,
            "status": self.status,
            "sequence": self.sequence,
            "last_modified": self.last_modified,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "property_name": self.property_name,
            "uid": self.uid,
            "recurrence_id": self.recurrence_id,
            "start": self.start,
            "end": self.end,
            "all_day": self.all_day,
            "summary": self.summary,
            "description": self.description,
            "status": self.status,
            "sequence": self.sequence,
            "last_modified": self.last_modified,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> NormalizedBooking:
        return cls(
            property_id=str(payload["property_id"]),
            property_name=str(payload["property_name"]),
            uid=str(payload["uid"]),
            recurrence_id=_none_or_str(payload.get("recurrence_id")),
            start=str(payload["start"]),
            end=str(payload["end"]),
            all_day=bool(payload["all_day"]),
            summary=_none_or_str(payload.get("summary")),
            description=_none_or_str(payload.get("description")),
            status=str(payload["status"]),
            sequence=_none_or_int(payload.get("sequence")),
            last_modified=_none_or_str(payload.get("last_modified")),
            source=_none_or_str(payload.get("source")),
        )


@dataclass(slots=True)
class BookingRecord:
    booking: NormalizedBooking
    content_fingerprint: str
    first_seen_at: str
    last_seen_at: str
    missing_polls: int = 0
    active: bool = True
    cancellation_reason: str | None = None
    inactive_since: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "booking": self.booking.to_dict(),
            "content_fingerprint": self.content_fingerprint,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "missing_polls": self.missing_polls,
            "active": self.active,
            "cancellation_reason": self.cancellation_reason,
            "inactive_since": self.inactive_since,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BookingRecord:
        return cls(
            booking=NormalizedBooking.from_dict(payload["booking"]),
            content_fingerprint=str(payload["content_fingerprint"]),
            first_seen_at=str(payload["first_seen_at"]),
            last_seen_at=str(payload["last_seen_at"]),
            missing_polls=int(payload.get("missing_polls", 0)),
            active=bool(payload.get("active", True)),
            cancellation_reason=_none_or_str(payload.get("cancellation_reason")),
            inactive_since=_none_or_str(payload.get("inactive_since")),
        )


@dataclass(slots=True)
class FeedCheckpoint:
    etag: str | None = None
    last_modified: str | None = None
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_content_hash: str | None = None
    consecutive_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "etag": self.etag,
            "last_modified": self.last_modified,
            "last_checked_at": self.last_checked_at,
            "last_success_at": self.last_success_at,
            "last_content_hash": self.last_content_hash,
            "consecutive_failures": self.consecutive_failures,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FeedCheckpoint:
        return cls(
            etag=_none_or_str(payload.get("etag")),
            last_modified=_none_or_str(payload.get("last_modified")),
            last_checked_at=_none_or_str(payload.get("last_checked_at")),
            last_success_at=_none_or_str(payload.get("last_success_at")),
            last_content_hash=_none_or_str(payload.get("last_content_hash")),
            consecutive_failures=int(payload.get("consecutive_failures", 0)),
        )


@dataclass(slots=True)
class MonitorState:
    schema_version: int = SCHEMA_VERSION
    updated_at: str | None = None
    feeds: dict[str, FeedCheckpoint] = field(default_factory=dict)
    bookings: dict[str, BookingRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "feeds": {key: value.to_dict() for key, value in sorted(self.feeds.items())},
            "bookings": {key: value.to_dict() for key, value in sorted(self.bookings.items())},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MonitorState:
        return cls(
            schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
            updated_at=_none_or_str(payload.get("updated_at")),
            feeds={
                str(key): FeedCheckpoint.from_dict(value)
                for key, value in (payload.get("feeds") or {}).items()
            },
            bookings={
                str(key): BookingRecord.from_dict(value)
                for key, value in (payload.get("bookings") or {}).items()
            },
        )


@dataclass(slots=True)
class DetectedChange:
    kind: ChangeKind
    booking: NormalizedBooking
    previous_booking: NormalizedBooking | None = None
    reason: str | None = None

    @property
    def reference(self) -> str:
        return self.booking.fingerprint[:8]


def _none_or_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _none_or_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
