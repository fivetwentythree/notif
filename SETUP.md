# Setup Guide

This guide walks through the full setup for the booking monitor using:

- iCal feeds as the booking source
- Discord webhooks for notifications
- GitHub Actions for scheduled polling

## 1. Prerequisites

You need:

- Python 3.13 available locally
- `uv` installed
- a GitHub repository for this project
- a Discord server where you can create a webhook
- one or more real iCal calendar URLs from your booking platforms

## 2. Configure the project locally

From the project root:

```bash
uv sync
```

This installs dependencies into `.venv`.

If you want to activate the environment manually:

```bash
source .venv/bin/activate
```

## 3. Add your property calendars

Edit `config/properties.yaml`.

Replace the placeholder entries with your real properties and iCal URLs:

```yaml
settings:
  request_timeout_seconds: 20
  fetch_retries: 3
  missing_threshold: 3
  tombstone_days: 30

properties:
  - id: beach-house
    name: Beach House
    source: airbnb
    calendar_url: "https://your-real-feed-url"
```

Field notes:

- `id`: stable internal identifier, do not change it casually after deployment
- `name`: display name used in Discord messages
- `source`: optional provider label such as `airbnb` or `booking-com`
- `calendar_url`: the actual `.ics` feed URL

## 4. Create the Discord webhook

In Discord:

1. Open the target server.
2. Open the target channel settings.
3. Go to `Integrations`.
4. Create a webhook.
5. Copy the webhook URL.

For local testing, export it in your shell:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

## 5. Run a local dry run

Start with a dry run so no Discord messages are sent:

```bash
uv run booking-monitor run --config config/properties.yaml --state-dir state --dry-run
```

What to expect:

- successful feeds will be parsed and compared
- a `state/state.json` file will be created
- no Discord messages will be sent

If your feed URLs are invalid, the command will log fetch failures.

## 6. Run a real local test

Once the dry run looks correct:

```bash
uv run booking-monitor run --config config/properties.yaml --state-dir state
```

If changes are detected and `DISCORD_WEBHOOK_URL` is set, the monitor will send Discord messages.

## 7. Push the project to GitHub

Create a repository and push this project to it.

The workflow file is already included:

- `.github/workflows/monitor.yml`

It is configured to run every 5 minutes.

## 8. Add the GitHub secret

In your GitHub repository:

1. Open `Settings`.
2. Open `Secrets and variables`.
3. Open `Actions`.
4. Create a new repository secret named `DISCORD_WEBHOOK_URL`.
5. Paste the Discord webhook URL as the value.

## 9. Enable workflow write permissions

The monitor persists state to a dedicated branch named `monitor-state`.

In GitHub repository settings:

1. Open `Settings`.
2. Open `Actions`.
3. Open `General`.
4. Under workflow permissions, enable `Read and write permissions`.

This is required because the workflow commits updated state back to GitHub.

## 10. Run the workflow the first time

You can wait for the schedule or trigger it manually:

1. Open the `Actions` tab.
2. Open the `Booking Monitor` workflow.
3. Click `Run workflow`.

On the first successful run, the workflow will:

- create the `monitor-state` branch if it does not already exist
- write `.state/state/state.json` inside that branch
- use that state file for future diffs

## 11. Verify the deployment

Check these points after the first run:

- the workflow completed successfully
- the `monitor-state` branch exists
- the state file was committed there
- Discord receives notifications when a booking changes

## 12. Recommended production settings

These values are a reasonable starting point in `config/properties.yaml`:

- `fetch_retries: 3`
- `missing_threshold: 3`
- `tombstone_days: 30`

Why:

- `fetch_retries` reduces transient network issues
- `missing_threshold` avoids false cancellations from one bad poll
- `tombstone_days` keeps cancelled records around long enough for reliable comparisons

## 13. Troubleshooting

No Discord messages:

- confirm `DISCORD_WEBHOOK_URL` is set locally or in GitHub secrets
- confirm changes were actually detected
- check the workflow logs for webhook HTTP errors

Workflow cannot persist state:

- confirm GitHub Actions has `Read and write permissions`
- confirm the repo allows the workflow to push commits

Bookings are incorrectly marked cancelled:

- increase `missing_threshold`
- inspect the raw provider feed and see whether cancelled events disappear entirely

Everything fails locally:

- confirm the iCal URLs are reachable
- confirm the feed returns valid `.ics` data
- run `uv run pytest` to verify the local environment is intact

## 14. Security notes

- Keep the repository private if the calendar feeds contain guest or booking details.
- Treat iCal URLs as secrets when they expose private reservation information.
- Never commit the Discord webhook URL into the repository.
