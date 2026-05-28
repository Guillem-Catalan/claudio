"""CLI: generate a meeting briefing for a deal.

Usage:
  python -m scripts.briefing --briefing-id <uuid>
  python -m scripts.briefing --deal-uuid <uuid> [--meeting-type <type>]
"""

import argparse

from src.pipelines.briefing.run import run


def main():
    parser = argparse.ArgumentParser(description="Generate meeting briefing")
    parser.add_argument("--briefing-id", help="Existing briefing row UUID")
    parser.add_argument("--deal-uuid", help="Deal UUID")
    parser.add_argument("--meeting-type", help="Override meeting type")
    args = parser.parse_args()

    if not args.briefing_id and not args.deal_uuid:
        parser.error("Either --briefing-id or --deal-uuid is required")

    run(
        briefing_id=args.briefing_id,
        deal_uuid=args.deal_uuid,
        meeting_type=args.meeting_type,
    )


if __name__ == "__main__":
    main()
