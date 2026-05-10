import sys

from src.pipelines.sync_notes.fetch import run

if __name__ == "__main__":
    deal_uuid = sys.argv[1]
    hs_deal_id = sys.argv[2]
    run(deal_uuid=deal_uuid, hs_deal_id=hs_deal_id)
