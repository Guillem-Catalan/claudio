"""
Unified Run Deals orchestrator.
Phases: sync HubSpot → atlas (new companies) → build context → snapshot + forecast.
"""

import traceback

from src.config import TEAMS, ALL_PARTNER_DOMAINS
from src.db.client import supabase
from src.pipelines.sync_deals.sync import run as sync_deals
from src.pipelines.sync_deal_context.run import run as sync_deal_context
from src.pipelines.front_deals.run import run as front_deals_snapshot
from src.pipelines.atlas.run import generate as atlas_generate
from src.pipelines.audit.run import run_single as audit_call

MAX_DEALS_PER_CYCLE = 30

_BACKFILL_ONLY_NAMES: set[str] = set()
for _t in TEAMS.values():
    if _t.get("backfill_only"):
        _BACKFILL_ONLY_NAMES |= _t.get("partner_names", set())

ACTIVE_STAGES = {
    "Factorial Project Alignment started",
    "Demo Booked", "Meeting Booked",
    "MEDDPICC Criteria Validation Started",
    "Economical Allignment Started", "Economical Alignment Started",
    "Pricing and Packaging", "Pricing & Packaging",
    "Contract Sent",
    "Discovery", "Product Alignment",
    "Pre-qualified", "Engaged", "Attempting to contact",
    "Associating the partner", "Research & Outreach",
    "New", "New Deals", "Opportunity detected",
    "On Hold", "Nurturing", "To reschedule", "To Reschedule",
    "Sales Nurturing", "Connected - Not Engaged",
}


def _audit_pending_calls(deal_uuid: str) -> int:
    """Find calls with transcript but no completed audit, and audit them inline."""
    result = supabase.rpc("check_calls_ready", {"p_deal_id": deal_uuid}).execute()
    if result.data:
        return 0

    calls_result = (
        supabase.table("calls")
        .select("id, call_id, rol")
        .eq("deal_id", deal_uuid)
        .not_.is_("transcript", "null")
        .not_.is_("rol", "null")
        .execute()
    )
    if not calls_result.data:
        return 0

    audited = 0
    for c in calls_result.data:
        call_uuid = c["id"]
        rol = c["rol"]
        audit_table = "pbd_audits" if rol == "PBD" else "pae_audits"
        existing = (
            supabase.table(audit_table)
            .select("win_rate_score")
            .eq("call_ref", call_uuid)
            .not_.is_("win_rate_score", "null")
            .limit(1)
            .execute()
        )
        if existing.data:
            continue
        print(f"    Auditing call {c['call_id']} ({rol}) ...")
        try:
            audit_call(c["call_id"])
            audited += 1
        except Exception as e:
            print(f"    Audit failed for {c['call_id']}: {e}")
    return audited


def _is_backfill_only(deal_name: str) -> bool:
    name_lower = (deal_name or "").lower()
    return any(pn in name_lower for pn in _BACKFILL_ONLY_NAMES)


_partner_website_cache: dict[str, bool] = {}


def _is_partner_company(deal: dict) -> bool:
    atlas_id = deal.get("atlas_id")
    if not atlas_id:
        return False
    if atlas_id in _partner_website_cache:
        return _partner_website_cache[atlas_id]
    result = supabase.table("atlas").select("website").eq("id", atlas_id).limit(1).execute()
    if not result.data:
        _partner_website_cache[atlas_id] = False
        return False
    website = (result.data[0].get("website") or "").lower()
    is_partner = any(domain in website for domain in ALL_PARTNER_DOMAINS)
    _partner_website_cache[atlas_id] = is_partner
    return is_partner


_STAGE_TO_BRIEF_USE_CASE = {
    "Demo Booked": "pae_brief_first_demo_multisector",
    "Meeting Booked": "pae_brief_first_demo_multisector",
    "Meeting scheduled": "pae_brief_first_demo_multisector",
    "Factorial Project Alignment started": "pae_brief_first_demo_multisector",
    "Product Alignment": "pae_brief_first_demo_multisector",
    "Discovery": "pae_brief_first_demo_multisector",
    "MEDDPICC Criteria Validation Started": "pae_brief_followup_meddic_multisector",
    "Economical Allignment Started": "pae_brief_pricing_closing_multisector",
    "Economical Alignment Started": "pae_brief_pricing_closing_multisector",
    "Pricing and Packaging": "pae_brief_pricing_closing_multisector",
    "Pricing & Packaging": "pae_brief_pricing_closing_multisector",
    "Contract Sent": "pae_brief_pricing_closing_multisector",
}


def _create_today_briefings() -> int:
    from datetime import date, datetime, timezone

    today = date.today().isoformat()
    deal_ids: set[str] = set()

    # Source 1: deals.hs_next_meeting_start_time = today
    r1 = (
        supabase.table("deals")
        .select("id")
        .gte("hs_next_meeting_start_time", today)
        .lt("hs_next_meeting_start_time", today + "T23:59:59")
        .execute()
    )
    deal_ids |= {d["id"] for d in (r1.data or [])}

    # Source 2: deal_meetings today
    r2 = (
        supabase.table("deal_meetings")
        .select("deal_id")
        .gte("meeting_start", today + "T00:00:00")
        .lt("meeting_start", today + "T23:59:59")
        .not_.is_("deal_id", "null")
        .execute()
    )
    deal_ids |= {d["deal_id"] for d in (r2.data or [])}

    # Source 3: calendar_meetings today (resolved)
    r3 = (
        supabase.table("calendar_meetings")
        .select("deal_id")
        .gte("meeting_start", today + "T00:00:00")
        .lt("meeting_start", today + "T23:59:59")
        .eq("resolved", True)
        .not_.is_("deal_id", "null")
        .execute()
    )
    deal_ids |= {d["deal_id"] for d in (r3.data or [])}

    if not deal_ids:
        return 0

    # Check which already have a briefing today
    existing = (
        supabase.table("briefings")
        .select("deal_id")
        .gte("created_at", today + "T00:00:00")
        .execute()
    )
    existing_ids = {d["deal_id"] for d in (existing.data or [])}
    new_ids = deal_ids - existing_ids

    if not new_ids:
        return 0

    # Fetch deal info for new briefings
    created = 0
    for deal_id in new_ids:
        deal = (
            supabase.table("deals")
            .select("id, deal_name, deal_stage")
            .eq("id", deal_id)
            .limit(1)
            .execute()
        )
        if not deal.data:
            continue

        d = deal.data[0]
        stage = d.get("deal_stage") or ""
        use_case = _STAGE_TO_BRIEF_USE_CASE.get(stage, "pae_brief_followup_meddic_multisector")

        supabase.table("briefings").insert({
            "deal_id": d["id"],
            "deal_name": d.get("deal_name") or "",
            "meeting_type": use_case.split("_")[2] if "_" in use_case else "follow_up",
            "use_case_key": use_case,
            "status": "pending",
        }).execute()
        created += 1

    return created


def _preload_partner_cache(atlas_ids: list[str]) -> None:
    """Batch preload atlas websites to avoid per-deal timeout."""
    ids_to_load = [a for a in atlas_ids if a and a not in _partner_website_cache]
    for i in range(0, len(ids_to_load), 50):
        batch = ids_to_load[i:i + 50]
        try:
            resp = supabase.table("atlas").select("id, website").in_("id", batch).execute()
            for a in (resp.data or []):
                website = (a.get("website") or "").lower()
                _partner_website_cache[a["id"]] = any(domain in website for domain in ALL_PARTNER_DOMAINS)
        except Exception:
            for aid in batch:
                _partner_website_cache[aid] = False


def _fetch_stale_deals(limit: int) -> list[dict]:
    stages = list(ACTIVE_STAGES)
    result = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, crm_id, atlas_id")
        .eq("context_stale", True)
        .in_("deal_stage", stages)
        .not_.is_("deal_context", "null")
        .order("updated_at", desc=False)
        .limit(limit * 2)
        .execute()
    )
    candidates = [d for d in (result.data or []) if not _is_backfill_only(d.get("deal_name", ""))]
    _preload_partner_cache([d.get("atlas_id") for d in candidates if d.get("atlas_id")])
    filtered = [d for d in candidates if not _is_partner_company(d)]
    return filtered[:limit]


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
        .limit(limit * 2)
        .execute()
    )
    candidates = [d for d in (result.data or []) if not _is_backfill_only(d.get("deal_name", ""))]
    _preload_partner_cache([d.get("atlas_id") for d in candidates if d.get("atlas_id")])
    filtered = [d for d in candidates if not _is_partner_company(d)]
    return filtered[:limit]


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
        print(f"  WARN: sync_deals failed: {e} — continuing with existing data")
        traceback.print_exc()

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
            ctx_result = sync_deal_context(deal_uuid, hs_deal_id)
            if isinstance(ctx_result, dict):
                context_complete = ctx_result.get("complete", False)
            else:
                context_complete = (ctx_result or 0) == 0

            # ── Phase 3b: Audit pending calls ────────────────────
            retried = _audit_pending_calls(deal_uuid)
            if retried:
                print(f"  ▸ AUDITS: {retried} pending calls audited")

            # ── Phase 4: Snapshot (only if context complete) ─────
            if context_complete:
                print(f"  ▸ SNAPSHOT: generating ...")
                front_deals_snapshot(deal_uuid, hs_deal_id)
                supabase.table("deals").update(
                    {"context_stale": False}
                ).eq("id", deal_uuid).execute()
            else:
                print(f"  ⏳ Context incomplete — skipping snapshot, will retry next cycle")
                pending_transcript += 1

            ok += 1

        except Exception as e:
            failed += 1
            failures.append(f"{deal_name}: {e}")
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()
            continue

    # ── Phase 5: Generate briefings for deals with meetings today ──
    print("\n▸ PHASE 5: BRIEFINGS")
    try:
        briefings_created = _create_today_briefings()
        if briefings_created:
            print(f"  {briefings_created} briefings created")
        else:
            print("  No new briefings needed")
    except Exception as e:
        print(f"  Briefings failed: {e}")

    # ── Phase 6: Compile trajectories for newly closed deals ────
    print(f"\n▸ PHASE 6: COMPILE TRAJECTORIES")
    try:
        from src.pipelines.intelligence.trajectories import compile_trajectory
        closed_resp = (
            supabase.table("deals")
            .select("id, deal_name, deal_stage")
            .in_("deal_stage", ["Closed Won", "Closed won", "Closed Won - Finance Only", "Closed Lost", "Closed lost", "Opportunity lost", "Opportunity Lost"])
            .not_.is_("id", "null")
            .execute()
        )
        compiled = 0
        for cd in (closed_resp.data or []):
            existing = supabase.table("deal_trajectories").select("id").eq("deal_id", cd["id"]).limit(1).execute()
            if not existing.data:
                result = compile_trajectory(cd["id"])
                if result:
                    compiled += 1
                    print(f"  Compiled: {cd['deal_name'][:50]} ({result['outcome']})")
                if compiled >= 10:
                    break
        print(f"  {compiled} new trajectories compiled")
    except Exception as e:
        print(f"  Trajectories failed: {e}")

    # ── Phase 7: Synthesize deal actions ────────────────────────
    print(f"\n▸ PHASE 7: SYNTHESIZE ACTIONS")
    try:
        from src.pipelines.actions.synthesize import synthesize_for_deal
        actions_ok = 0
        for deal in all_stale[:MAX_DEALS_PER_CYCLE]:
            try:
                result = synthesize_for_deal(deal["id"])
                if result:
                    actions_ok += 1
            except Exception as e:
                print(f"  Action synthesis failed for {deal.get('deal_name', '?')[:30]}: {e}")
        print(f"  {actions_ok} actions synthesized")
    except Exception as e:
        print(f"  Actions phase failed: {e}")

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"RUN DEALS COMPLETE: {ok} OK, {failed} failed, {pending_transcript} pending transcript")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
    print("=" * 60)
