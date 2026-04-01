from __future__ import annotations

import argparse
import logging
import os

from booking_monitor.config import load_config
from booking_monitor.notifiers.discord import DiscordNotifier
from booking_monitor.runner import MonitorRunner
from booking_monitor.storage import JsonStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor iCal booking feeds and notify Discord.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Poll feeds, detect changes, and notify Discord.")
    run_parser.add_argument(
        "--config",
        default=os.environ.get("MONITOR_CONFIG", "config/properties.yaml"),
        help="Path to the YAML config file.",
    )
    run_parser.add_argument(
        "--state-dir",
        default=os.environ.get("MONITOR_STATE_DIR", "state"),
        help="Directory where state.json is stored.",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run detection without sending Discord notifications.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command != "run":
        parser.error(f"unsupported command: {args.command}")

    config = load_config(args.config)
    state_store = JsonStateStore(args.state_dir)
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    notifier = DiscordNotifier(webhook_url) if webhook_url else None

    summary = MonitorRunner(config=config, state_store=state_store, notifier=notifier).run(
        dry_run=args.dry_run
    )

    logging.info(
        "completed run: successful=%s not_modified=%s failed=%s changes=%s",
        summary.successful_feeds,
        summary.not_modified_feeds,
        summary.failed_feeds,
        len(summary.changes),
    )

    if summary.failed_feeds and summary.successful_feeds == 0 and summary.not_modified_feeds == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
