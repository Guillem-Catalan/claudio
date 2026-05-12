"""Entry point for front_deals snapshot generation (single deal)."""

import argparse

from src.pipelines.front_deals.run import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-uuid", required=True)
    parser.add_argument("--hs-deal-id", required=True)
    args = parser.parse_args()

    run(deal_uuid=args.deal_uuid, hs_deal_id=args.hs_deal_id)


if __name__ == "__main__":
    main()
