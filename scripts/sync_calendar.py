"""Entry point for sync_calendar pipeline."""

import argparse

from src.pipelines.sync_calendar.run import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["full", "refresh"],
        default="full",
        help="full = reconcile yesterday + sync today, refresh = sync today only",
    )
    args = parser.parse_args()
    run(mode=args.mode)
