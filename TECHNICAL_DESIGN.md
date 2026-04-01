# Technical Design

## Goals

- Poll multiple property calendars via iCal
- Detect new bookings, updates, and cancellations
- Notify a Discord server
- Stay free by using GitHub Actions as the scheduler
- Maximize reliability within the limits of poll-based feeds

## Constraints

- iCal feeds are pull-only, so detection is bounded by poll interval
- GitHub Actions runners are ephemeral and stateless
- Discord webhooks are simple HTTP endpoints without idempotency keys
- Free hosting rules out managed databases and always-on workers

## Architecture

1. GitHub Actions runs every 5 minutes.
2. The workflow checks out the code branch and a dedicated state branch named `monitor-state`.
3. The monitor fetches each feed with conditional HTTP headers (`If-None-Match`, `If-Modified-Since`) when possible.
4. Each `VEVENT` is normalized into a canonical booking representation.
5. The detector compares the current snapshot with the last persisted snapshot.
6. Detected changes are grouped into a Discord message batch.
7. After successful notification, the updated state is committed back to `monitor-state`.

## State model

The persisted state file stores:

- feed checkpoints: `etag`, `last_modified`, `last_checked_at`, `last_success_at`, `consecutive_failures`
- booking records keyed by `property_id + uid + recurrence_id`
- lifecycle fields: `first_seen_at`, `last_seen_at`, `missing_polls`, `active`, `inactive_since`
- the last normalized booking payload and its fingerprint

This allows the detector to distinguish between:

- a truly new booking
- a changed booking with the same stable identity
- a booking explicitly cancelled in the feed
- a booking that vanished from the feed for several consecutive polls

## Booking identity and fingerprints

Stable identity:

- `property_id`
- `UID`
- `RECURRENCE-ID` when present

Change fingerprint:

- start/end
- all-day flag
- summary
- description
- normalized status
- sequence
- last-modified

Using a stable identity plus a content fingerprint prevents treating every edit as a new booking.

## Cancellation strategy

Two cancellation modes are supported:

1. Explicit cancellation
   The event is still present but marked `STATUS:CANCELLED` or `STATUS:CANCELED`.
2. Implicit cancellation
   The event disappears from the feed. The detector increments `missing_polls`. Once the configured threshold is reached, the booking is treated as cancelled.

The second path matters because many providers drop cancelled bookings entirely instead of publishing a cancelled event revision.

## Reliability model

This scaffold aims for at-least-once detection, not exactly-once delivery.

- State is only persisted after Discord delivery succeeds.
- If Discord delivery fails, the same changes are retried on the next run.
- If Discord delivery succeeds but the state commit fails, duplicate notifications are possible on the next run.
- Each notification line includes a short reference derived from the booking fingerprint to make duplicates easier to spot.

## GitHub Actions design

- schedule: every 5 minutes
- concurrency: one monitor run per ref at a time
- persistence: dedicated `monitor-state` branch
- permissions: `contents: write`

This avoids overloading the default branch with machine-generated commits while keeping the state durable across ephemeral runners.

## Security notes

- Real booking data should not live in a public repo.
- Store the Discord webhook URL in a GitHub Actions secret, never in `config/properties.yaml`.
- Assume calendar URLs are sensitive if they expose reservation details.

## Recommended next steps

1. Replace placeholder iCal URLs in `config/properties.yaml`.
2. Run locally in `--dry-run` mode and inspect the generated `state/state.json`.
3. Push to GitHub and enable the workflow.
4. Add provider-specific normalization rules once you see real feed payloads.
