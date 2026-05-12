import sys

from src.pipelines.sync_deal_context.run import run

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.sync_deal_context <deal_uuid> <hs_deal_id>")
        sys.exit(1)

    run(deal_uuid=sys.argv[1], hs_deal_id=sys.argv[2])
