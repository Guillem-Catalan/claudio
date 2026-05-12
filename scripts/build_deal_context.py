import sys

from src.pipelines.build_deal_context.run import run

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.build_deal_context <deal_uuid> <hs_deal_id> [emails|notes|all]")
        sys.exit(1)

    deal_uuid = sys.argv[1]
    hs_deal_id = sys.argv[2]
    context_type = sys.argv[3] if len(sys.argv) > 3 else "all"
    run(deal_uuid=deal_uuid, hs_deal_id=hs_deal_id, context_type=context_type)
