"""
Weekly activity digest for TL.

Usage:
  python -m scripts.weekly_digest                                        # all PAEs, previous week
  python -m scripts.weekly_digest --pae-email david.clemente@factorial.co
  python -m scripts.weekly_digest --week-start 2026-05-26
  python -m scripts.weekly_digest --channel C0ATY3V8CN4                  # override Slack channel
"""

import argparse
from datetime import date

from src.pipelines.weekly_digest.run import run_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pae-email", help="Single PAE email (default: all Santander/Telefónica)")
    parser.add_argument("--week-start", help="Monday of target week YYYY-MM-DD (default: previous week)")
    parser.add_argument("--channel", help="Override Slack channel ID (for testing)")
    args = parser.parse_args()

    ws = date.fromisoformat(args.week_start) if args.week_start else None
    run_all(pae_email=args.pae_email, week_start=ws, channel_override=args.channel)


if __name__ == "__main__":
    main()
