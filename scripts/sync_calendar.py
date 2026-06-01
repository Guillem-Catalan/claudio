"""Entry point for sync_calendar pipeline."""

import argparse
from datetime import datetime, timedelta, timezone

from src.pipelines.sync_calendar.run import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["full", "refresh"],
        default="full",
        help="full = reconcile yesterday + sync today, refresh = sync today only",
    )
    parser.add_argument(
        "--date",
        help="target date YYYY-MM-DD (default: today in CEST). Simulates running at 00:00 CEST on that date.",
    )
    args = parser.parse_args()

    target = None
    if args.date:
        local_dt = datetime.strptime(args.date, "%Y-%m-%d")
        target = local_dt.replace(tzinfo=timezone.utc) - timedelta(hours=2)

    run(mode=args.mode, target_date=target)
