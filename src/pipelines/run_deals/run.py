"""
Unified Run Deals orchestrator.
Phases: sync HubSpot → atlas (new companies) → build context → snapshot + forecast.
"""

import traceback

from src.db.client import supabase
from src.pipelines.sync_deals.sync import run as sync_deals
from src.pipelines.sync_deal_context.run import run as sync_deal_context
from src.pipelines.front_deals.run import run as front_deals_snapshot
from src.pipelines.atlas.run import generate as atlas_generate

MAX_DEALS_PER_CYCLE = 30

ACTIVE_STAGES = {
    "Factorial Project Alignment started",
    "Demo Booked", "Meeting Booked",
    "MEDDPICC Criteria Validation Started",
    "Economical Allignment Started",
    "Pricing and Packaging", "Pricing & Packaging",
    "Contract Sent",
    "Discovery", "Product Alignment",
    "Pre-qualified", "Engaged", "Attempting to contact",
    "Associating the partner", "Research & Outreach",
    "New", "New Deals", "Opportunity detected",
    "On Hold", "Nurturing", "To reschedule",
    "Sales Nurturing", "Connected - Not Engaged",
}


def _fetch_stale_deals(limit: int) -> list[dict]:
    stages = list(ACTIVE_STAGES)
    result = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, crm_id, atlas_id")
        .eq("context_stale", True)
        .in_("deal_stage", stages)
        .not_.is_("deal_context", "null")
        .order("updated_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _fetch_stale_deals_no_context(limit: int) -> list[dict]:
    """Deals marked stale that have no context yet (new deals)."""
    stages = list(ACTIVE_STAGES)
    result = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, crm_id, atlas_id")
        .eq("context_stale", True)
        .in_("deal_stage", stages)
        .is_("deal_context", "null")
        .order("updated_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _needs_atlas(deal: dict) -> bool:
    atlas_id = deal.get("atlas_id")
    if not atlas_id:
        return False
    result = (
        supabase.table("atlas")
        .select("last_generated")
        .eq("id", atlas_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return False
    return result.data.get("last_generated") is None


def run(full: bool = False):
    print("=" * 60)
    print("RUN DEALS — Unified Pipeline")
    print("=" * 60)

    # ── Phase 1: Sync deals from HubSpot ─────────────────────────
    print("\n▸ PHASE 1: SYNC")
    try:
        sync_deals(full=full)
    except Exception as e:
        print(f"  FATAL: sync_deals failed: {e}")
        traceback.print_exc()
        return

    # ── Phase 2+3+4: Process stale deals ─────────────────────────
    stale = _fetch_stale_deals(MAX_DEALS_PER_CYCLE)
    stale_no_ctx = _fetch_stale_deals_no_context(max(0, MAX_DEALS_PER_CYCLE - len(stale)))
    all_stale = stale + stale_no_ctx

    if not all_stale:
        print("\n▸ No stale deals to process.")
        return

    print(f"\n▸ {len(all_stale)} stale deals to process (cap {MAX_DEALS_PER_CYCLE})")

    ok = 0
    failed = 0
    pending_transcript = 0
    failures: list[str] = []

    for i, deal in enumerate(all_stale, 1):
        deal_uuid = deal["id"]
        hs_deal_id = deal["deal_id"]
        deal_name = deal.get("deal_name", "?")
        print(f"\n{'─' * 50}")
        print(f"  [{i}/{len(all_stale)}] {deal_name}")

        try:
            # ── Phase 2: Atlas if needed ─────────────────────────
            if _needs_atlas(deal):
                atlas_id = deal["atlas_id"]
                crm_id = deal.get("crm_id")
                print(f"  ▸ ATLAS: generating for {atlas_id} (crm_id={crm_id})")
                atlas_generate(atlas_id, crm_id)

            # ── Phase 3: Build context ───────────────────────────
            print(f"  ▸ CONTEXT: building deal_context ...")
            meetings_skipped = sync_deal_context(deal_uuid, hs_deal_id) or 0

            # ── Phase 4: Snapshot + forecast ─────────────────────
            print(f"  ▸ SNAPSHOT: generating ...")
            front_deals_snapshot(deal_uuid, hs_deal_id)

            # ── Mark as processed ────────────────────────────────
            if meetings_skipped > 0:
                print(f"  ⏳ {meetings_skipped} meetings pending transcript — will retry next cycle")
                pending_transcript += 1
            else:
                supabase.table("deals").update(
                    {"context_stale": False}
                ).eq("id", deal_uuid).execute()

            ok += 1

        except Exception as e:
            failed += 1
            failures.append(f"{deal_name}: {e}")
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()
            continue

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"RUN DEALS COMPLETE: {ok} OK, {failed} failed, {pending_transcript} pending transcript")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
    print("=" * 60)
