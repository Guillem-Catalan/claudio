"""
Backfill a new team's deals independently from run_deals.

Usage:
  python -m scripts.backfill_team --team TIM                          # all phases, limit 50
  python -m scripts.backfill_team --team TIM --phase sync             # only sync deals
  python -m scripts.backfill_team --team TIM --phase context --limit 20
  python -m scripts.backfill_team --team TIM --phase snapshot --limit 10
"""

import argparse

from src.pipelines.backfill_team.run import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", required=True, help="Team name (e.g., TIM, TELEKOM)")
    parser.add_argument("--phase", default="all", choices=["sync", "context", "snapshot", "all"])
    parser.add_argument("--limit", type=int, default=50, help="Max deals per phase")
    args = parser.parse_args()

    run(team=args.team, phase=args.phase, limit=args.limit)


if __name__ == "__main__":
    main()
