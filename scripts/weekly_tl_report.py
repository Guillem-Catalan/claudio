"""
Weekly TL Report — unified per-PAE (activity + pipeline review).

Usage:
  python -m scripts.weekly_tl_report --pae-email xavier.fortuny@factorial.co
  python -m scripts.weekly_tl_report --pae-email xavier.fortuny@factorial.co --week-start 2026-06-02
  python -m scripts.weekly_tl_report --pae-email xavier.fortuny@factorial.co --channel C0ATY3V8CN4
"""

import argparse
from datetime import date

from src.pipelines.weekly_tl_report.run import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pae-email", required=True, help="PAE email")
    parser.add_argument("--week-start", help="Monday YYYY-MM-DD (default: previous week)")
    parser.add_argument("--channel", help="Override Slack channel ID (for testing)")
    args = parser.parse_args()

    ws = date.fromisoformat(args.week_start) if args.week_start else None
    run(pae_email=args.pae_email, week_start=ws, channel_override=args.channel)


if __name__ == "__main__":
    main()
