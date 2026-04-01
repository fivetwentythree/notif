# Booking Monitor

This scaffold polls multiple iCal feeds, detects booking changes with persistent state, and posts summaries to a Discord webhook.

## Why this shape

GitHub Actions is only a scheduler and runner. The hard part is durable state across runs, so this scaffold persists a machine-readable state file on a dedicated branch (`monitor-state`) and uses that state to detect:

- new bookings
- updates to existing bookings
- explicit cancellations (`STATUS:CANCELLED`)
- implicit cancellations when a booking disappears for `N` consecutive polls

## Local setup

1. Edit `config/properties.yaml`.
2. Set `DISCORD_WEBHOOK_URL`.
3. Install dependencies:

```bash
uv sync
```

4. Run once locally:

```bash
uv run booking-monitor run --config config/properties.yaml --state-dir state
```

5. Dry run without sending Discord messages:

```bash
uv run booking-monitor run --config config/properties.yaml --state-dir state --dry-run
```

## GitHub Actions setup

1. Put the repository on GitHub.
2. Add the repository secret `DISCORD_WEBHOOK_URL`.
3. Keep the repo private if the calendar data is sensitive.
4. Enable Actions write permission for contents, because the workflow persists state to `monitor-state`.
5. Update `config/properties.yaml` with real iCal URLs.

The included workflow runs every 5 minutes and will auto-create the `monitor-state` branch on first run.

## Important caveats

- GitHub Actions schedules are not real-time and can be delayed.
- Discord webhooks do not offer transactional delivery, so this design is best-effort with at-least-once semantics.
- If a provider silently removes cancelled events instead of publishing `STATUS:CANCELLED`, detection depends on the `missing_threshold` value.
