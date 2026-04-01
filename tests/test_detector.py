from __future__ import annotations

from booking_monitor.config import PropertyConfig
from booking_monitor.detector import apply_property_snapshot
from booking_monitor.models import ChangeKind, DetectedChange, MonitorState, NormalizedBooking
from booking_monitor.notifiers.discord import _build_payloads


PROPERTY = PropertyConfig(
    id="beach-house",
    name="Beach House",
    source="airbnb",
    calendar_url="https://example.invalid/feed.ics",
)


def make_booking(
    *,
    uid: str = "abc123",
    start: str = "2026-04-10",
    end: str = "2026-04-14",
    summary: str = "Reservation",
    status: str = "CONFIRMED",
    sequence: int | None = 1,
) -> NormalizedBooking:
    return NormalizedBooking(
        property_id=PROPERTY.id,
        property_name=PROPERTY.name,
        uid=uid,
        recurrence_id=None,
        start=start,
        end=end,
        all_day=True,
        summary=summary,
        description=None,
        status=status,
        sequence=sequence,
        last_modified="2026-03-31T10:00:00+00:00",
        source=PROPERTY.source,
    )


def test_detects_new_booking() -> None:
    state = MonitorState()

    changes = apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[make_booking()],
        observed_at="2026-03-31T11:00:00+00:00",
        missing_threshold=3,
        tombstone_days=30,
    )

    assert [change.kind for change in changes] == [ChangeKind.NEW]


def test_detects_update_for_existing_booking() -> None:
    state = MonitorState()
    apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[make_booking(summary="Guest A")],
        observed_at="2026-03-31T11:00:00+00:00",
        missing_threshold=3,
        tombstone_days=30,
    )

    changes = apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[make_booking(summary="Guest B", sequence=2)],
        observed_at="2026-03-31T11:05:00+00:00",
        missing_threshold=3,
        tombstone_days=30,
    )

    assert [change.kind for change in changes] == [ChangeKind.UPDATED]


def test_detects_explicit_cancellation() -> None:
    state = MonitorState()
    apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[make_booking()],
        observed_at="2026-03-31T11:00:00+00:00",
        missing_threshold=3,
        tombstone_days=30,
    )

    changes = apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[make_booking(status="CANCELLED")],
        observed_at="2026-03-31T11:05:00+00:00",
        missing_threshold=3,
        tombstone_days=30,
    )

    assert [change.kind for change in changes] == [ChangeKind.CANCELLED]


def test_detects_implicit_cancellation_after_threshold() -> None:
    state = MonitorState()
    apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[make_booking()],
        observed_at="2026-03-31T11:00:00+00:00",
        missing_threshold=2,
        tombstone_days=30,
    )

    first_missing = apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[],
        observed_at="2026-03-31T11:05:00+00:00",
        missing_threshold=2,
        tombstone_days=30,
    )
    second_missing = apply_property_snapshot(
        state=state,
        property_config=PROPERTY,
        current_events=[],
        observed_at="2026-03-31T11:10:00+00:00",
        missing_threshold=2,
        tombstone_days=30,
    )

    assert first_missing == []
    assert [change.kind for change in second_missing] == [ChangeKind.CANCELLED]


def test_discord_payload_skips_not_available_entries_and_ref_codes() -> None:
    changes = [
        DetectedChange(kind=ChangeKind.UPDATED, booking=make_booking(summary="Airbnb (Not available)")),
        DetectedChange(kind=ChangeKind.UPDATED, booking=make_booking(uid="def456", summary="Reserved")),
    ]

    payloads = _build_payloads(changes)

    assert len(payloads) == 1
    content = str(payloads[0]["content"])
    assert "Airbnb (Not available)" not in content
    assert "Reserved" in content
    assert "ref " not in content


def test_discord_payload_keeps_cancellations_even_when_summary_is_not_available() -> None:
    changes = [
        DetectedChange(kind=ChangeKind.CANCELLED, booking=make_booking(summary="Airbnb (Not available)")),
    ]

    payloads = _build_payloads(changes)

    assert len(payloads) == 1
    content = str(payloads[0]["content"])
    assert "CANCELLED" in content
    assert "Airbnb (Not available)" in content
