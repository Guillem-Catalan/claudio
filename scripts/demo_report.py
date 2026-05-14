"""
Weekly demo coaching report.

Usage:
  python -m scripts.demo_report                                      # all PAEs, previous week
  python -m scripts.demo_report --pae-email xavier.fortuny@factorial.co
  python -m scripts.demo_report --week-start 2026-05-05
"""

import argparse
from datetime import date

from src.pipelines.demo_evaluation.weekly_report import run_weekly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pae-email", help="Single PAE email (default: all Santander/Telefónica)")
    parser.add_argument("--week-start", help="Monday of target week YYYY-MM-DD (default: previous week)")
    args = parser.parse_args()

    ws = date.fromisoformat(args.week_start) if args.week_start else None
    run_weekly(pae_email=args.pae_email, week_start=ws)


if __name__ == "__main__":
    main()
