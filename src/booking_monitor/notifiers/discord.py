from __future__ import annotations

from collections.abc import Iterable
import json
import logging
import time

import httpx

from booking_monitor.models import ChangeKind, DetectedChange


logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, webhook_url: str, timeout_seconds: int = 15, retries: int = 3) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.retries = max(1, retries)

    def send_changes(self, changes: Iterable[DetectedChange], dry_run: bool = False) -> None:
        change_list = sorted(
            [change for change in changes if _should_notify(change)],
            key=lambda item: (item.booking.property_name, item.booking.start, item.booking.booking_key),
        )
        if not change_list:
            return

        payloads = _build_payloads(change_list)
        if dry_run:
            for payload in payloads:
                logger.info("discord dry-run payload: %s", json.dumps(payload, indent=2))
            return

        for payload in payloads:
            self._post(payload)

    def _post(self, payload: dict[str, object]) -> None:
        for attempt in range(1, self.retries + 1):
            try:
                response = httpx.post(self.webhook_url, json=payload, timeout=self.timeout_seconds)
                if response.status_code in (200, 204):
                    return

                if response.status_code == 429 and attempt < self.retries:
                    retry_after = _parse_retry_after(response)
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500 and attempt < self.retries:
                    time.sleep(min(2**attempt, 5))
                    continue

                response.raise_for_status()
            except httpx.HTTPError:
                if attempt >= self.retries:
                    raise
                time.sleep(min(2**attempt, 5))


def _build_payloads(changes: list[DetectedChange]) -> list[dict[str, object]]:
    changes = [change for change in changes if _should_notify(change)]
    if not changes:
        return []

    header = f"Booking monitor detected {len(changes)} change(s)."
    lines = [_format_change_line(change) for change in changes]

    payloads: list[dict[str, object]] = []
    current_lines = [header]
    current_length = len(header) + 1

    for line in lines:
        line_length = len(line) + 1
        if current_length + line_length > 1800 and len(current_lines) > 1:
            payloads.append({"content": "\n".join(current_lines)})
            current_lines = [header, line]
            current_length = len(header) + len(line) + 2
            continue

        current_lines.append(line)
        current_length += line_length

    if current_lines:
        payloads.append({"content": "\n".join(current_lines)})

    return payloads


def _format_change_line(change: DetectedChange) -> str:
    label = {
        ChangeKind.NEW: "NEW",
        ChangeKind.UPDATED: "UPDATED",
        ChangeKind.CANCELLED: "CANCELLED",
    }[change.kind]
    booking = change.booking
    summary = booking.summary or booking.uid
    return f"- {label} | {booking.property_name} | {booking.start} -> {booking.end} | {summary}"


def _should_notify(change: DetectedChange) -> bool:
    if change.kind == ChangeKind.CANCELLED:
        return True

    summary = (change.booking.summary or "").strip().lower()
    if not summary:
        return True
    return "not available" not in summary


def _parse_retry_after(response: httpx.Response) -> float:
    header = response.headers.get("Retry-After")
    if header:
        return max(float(header), 1.0)

    try:
        payload = response.json()
    except ValueError:
        return 1.0

    retry_after = payload.get("retry_after", 1)
    return max(float(retry_after), 1.0)
