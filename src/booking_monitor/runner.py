from __future__ import annotations

from dataclasses import dataclass, field
import logging

from booking_monitor.config import MonitorConfig
from booking_monitor.detector import apply_property_snapshot
from booking_monitor.ical import CalendarClient, parse_calendar
from booking_monitor.models import DetectedChange, FeedCheckpoint, MonitorState
from booking_monitor.notifiers.discord import DiscordNotifier
from booking_monitor.storage import JsonStateStore


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunSummary:
    successful_feeds: int = 0
    not_modified_feeds: int = 0
    failed_feeds: int = 0
    changes: list[DetectedChange] = field(default_factory=list)


class MonitorRunner:
    def __init__(
        self,
        config: MonitorConfig,
        state_store: JsonStateStore,
        notifier: DiscordNotifier | None,
    ) -> None:
        self.config = config
        self.state_store = state_store
        self.notifier = notifier
        self.client = CalendarClient(
            timeout_seconds=config.settings.request_timeout_seconds,
            retries=config.settings.fetch_retries,
        )

    def run(self, dry_run: bool = False) -> RunSummary:
        state = self.state_store.load()
        summary = RunSummary()
        state_changed = False

        for property_config in self.config.properties:
            checkpoint = state.feeds.get(property_config.id, FeedCheckpoint())
            result = self.client.fetch(property_config, checkpoint)
            checkpoint.last_checked_at = result.observed_at
            state.feeds[property_config.id] = checkpoint

            if result.kind == "failed":
                checkpoint.consecutive_failures += 1
                summary.failed_feeds += 1
                state_changed = True
                logger.warning("fetch failed for %s: %s", property_config.id, result.error)
                continue

            checkpoint.consecutive_failures = 0
            checkpoint.last_success_at = result.observed_at
            checkpoint.etag = result.etag or checkpoint.etag
            checkpoint.last_modified = result.last_modified or checkpoint.last_modified

            if result.kind == "not_modified":
                summary.not_modified_feeds += 1
                state_changed = True
                continue

            if result.text is None:
                summary.failed_feeds += 1
                checkpoint.consecutive_failures += 1
                state_changed = True
                logger.warning("empty calendar payload for %s", property_config.id)
                continue

            try:
                checkpoint.last_content_hash = result.body_hash
                current_events = parse_calendar(property_config, result.text)
                changes = apply_property_snapshot(
                    state=state,
                    property_config=property_config,
                    current_events=current_events,
                    observed_at=result.observed_at,
                    missing_threshold=self.config.settings.missing_threshold,
                    tombstone_days=self.config.settings.tombstone_days,
                )
            except Exception as exc:
                checkpoint.consecutive_failures += 1
                summary.failed_feeds += 1
                state_changed = True
                logger.warning("processing failed for %s: %s", property_config.id, exc)
                continue

            summary.successful_feeds += 1
            summary.changes.extend(changes)
            state_changed = True

        if summary.changes:
            if self.notifier is None and not dry_run:
                raise ValueError("DISCORD_WEBHOOK_URL must be set unless --dry-run is used")
            if self.notifier is not None:
                self.notifier.send_changes(summary.changes, dry_run=dry_run)

        if state_changed:
            self.state_store.save(state)

        return summary
