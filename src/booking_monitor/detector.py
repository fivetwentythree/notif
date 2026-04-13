from __future__ import annotations

from booking_monitor.config import PropertyConfig
from booking_monitor.models import (
    BookingRecord,
    ChangeKind,
    DetectedChange,
    MonitorState,
    NormalizedBooking,
    parse_datetime,
)


CANCELLED_STATUSES = {"CANCELLED", "CANCELED"}


def apply_property_snapshot(
    state: MonitorState,
    property_config: PropertyConfig,
    current_events: list[NormalizedBooking],
    observed_at: str,
    missing_threshold: int,
    tombstone_days: int,
) -> list[DetectedChange]:
    changes: list[DetectedChange] = []
    current_by_key = {event.booking_key: event for event in current_events}
    property_keys = [
        key for key, record in state.bookings.items() if record.booking.property_id == property_config.id
    ]

    for booking in current_events:
        record = state.bookings.get(booking.booking_key)
        cancelled = booking.status.upper() in CANCELLED_STATUSES

        if record is None:
            state.bookings[booking.booking_key] = BookingRecord(
                booking=booking,
                content_fingerprint=booking.fingerprint,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                active=not cancelled,
                cancellation_reason="explicit_status" if cancelled else None,
                inactive_since=observed_at if cancelled else None,
            )
            if not cancelled:
                changes.append(DetectedChange(kind=ChangeKind.NEW, booking=booking))
            continue

        previous_booking = record.booking
        previous_fingerprint = previous_booking.fingerprint
        was_active = record.active

        record.booking = booking
        record.content_fingerprint = booking.fingerprint
        record.last_seen_at = observed_at
        record.missing_polls = 0

        if cancelled:
            record.active = False
            record.cancellation_reason = "explicit_status"
            record.inactive_since = observed_at
            if was_active:
                changes.append(
                    DetectedChange(
                        kind=ChangeKind.CANCELLED,
                        booking=booking,
                        previous_booking=previous_booking,
                        reason="explicit_status",
                    )
                )
            continue

        record.active = True
        record.cancellation_reason = None
        record.inactive_since = None

        if not was_active:
            changes.append(
                DetectedChange(
                    kind=ChangeKind.UPDATED,
                    booking=booking,
                    previous_booking=previous_booking,
                    reason="reappeared",
                )
            )
            continue

        if previous_fingerprint != booking.fingerprint:
            changes.append(
                DetectedChange(
                    kind=ChangeKind.UPDATED,
                    booking=booking,
                    previous_booking=previous_booking,
                    reason="content_changed",
                )
            )

    observed_dt = parse_datetime(observed_at)

    for key in property_keys:
        if key in current_by_key:
            continue

        record = state.bookings[key]
        if not record.active:
            continue

        # If the booking's end date has already passed, it naturally dropped
        # off the iCal feed — silently mark it inactive instead of reporting
        # it as a cancellation.
        booking_end = parse_datetime(record.booking.end)
        if observed_dt and booking_end:
            # Normalise both sides to naive so date-only and tz-aware
            # strings can be compared safely.
            end_naive = booking_end.replace(tzinfo=None) if booking_end.tzinfo else booking_end
            obs_naive = observed_dt.replace(tzinfo=None) if observed_dt.tzinfo else observed_dt
            if end_naive <= obs_naive:
                record.active = False
                record.cancellation_reason = "expired"
                record.inactive_since = observed_at
                continue

        record.missing_polls += 1
        if record.missing_polls >= missing_threshold:
            record.active = False
            record.cancellation_reason = "missing_from_feed"
            record.inactive_since = observed_at
            changes.append(
                DetectedChange(
                    kind=ChangeKind.CANCELLED,
                    booking=record.booking,
                    previous_booking=record.booking,
                    reason="missing_from_feed",
                )
            )

    _prune_inactive_records(state, property_config.id, observed_at, tombstone_days)
    return changes


def _prune_inactive_records(
    state: MonitorState,
    property_id: str,
    observed_at: str,
    tombstone_days: int,
) -> None:
    if tombstone_days <= 0:
        return

    observed = parse_datetime(observed_at)
    if observed is None:
        return

    removable: list[str] = []
    for key, record in state.bookings.items():
        if record.booking.property_id != property_id or record.active or not record.inactive_since:
            continue

        inactive_since = parse_datetime(record.inactive_since)
        if inactive_since is None:
            continue

        age_days = (observed - inactive_since).days
        if age_days >= tombstone_days:
            removable.append(key)

    for key in removable:
        del state.bookings[key]
