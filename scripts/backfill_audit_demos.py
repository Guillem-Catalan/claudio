"""
Backfill audit_demos for specific calls that already have pae_audits.

Usage: python -m scripts.backfill_audit_demos <call_id> [<call_id> ...]
"""

import sys

from src.db.client import supabase
from src.pipelines.audit.context import get_deal_context
from src.pipelines.demo_evaluation.run import run as run_demo_eval


def main():
    call_ids = sys.argv[1:]
    if not call_ids:
        print("Usage: python -m scripts.backfill_audit_demos <call_id> [...]")
        sys.exit(1)

    for call_id in call_ids:
        print(f"\n=== Call {call_id} ===")

        call_resp = (
            supabase.table("calls")
            .select("*")
            .eq("call_id", call_id)
            .limit(1)
            .execute()
        )
        if not call_resp.data:
            print(f"  Not found")
            continue
        call = call_resp.data[0]

        existing = (
            supabase.table("audit_demos")
            .select("id")
            .eq("call_ref", call["id"])
            .limit(1)
            .execute()
        )
        if existing.data:
            print(f"  Already in audit_demos — skipping")
            continue

        pae_audit_resp = (
            supabase.table("pae_audits")
            .select("*")
            .eq("call_ref", call["id"])
            .limit(1)
            .execute()
        )
        pae_audit = pae_audit_resp.data[0] if pae_audit_resp.data else {}

        deal_context = get_deal_context(
            call.get("deal_id"), call.get("fecha", ""), "PAE"
        )

        try:
            run_demo_eval(call, pae_audit, deal_context)
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
