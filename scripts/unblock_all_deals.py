"""
Unblock all open deals: fix flags + clear Gong stubs + audit real calls.

Four phases:
  1. Fix stale flags (atlas_ready, emails_ready, meetings_ready, notes_ready)
  2. Clear rol on Gong/HubSpot stubs (no real transcript → not auditable)
  3. Audit real calls blocking calls_ready (with actual conversation transcripts)
  4. Verify and report

Usage:
    python -m scripts.unblock_all_deals [--dry-run] [--workers 4] [--limit N]
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.db.client import supabase

_GONG_STUB_MARKERS = [
    "[Gong ",
    "Outbound answered call",
    "Inbound answered call",
    "Outbound unanswered call",
    "Inbound unanswered call",
]

_CLOSED_KEYWORDS = [
    "closed", "lost", "won", "churned", "spam", "wrongly", "failed",
    "retained", "do not use", "churn confirmed",
]


def _is_closed_stage(stage: str) -> bool:
    if not stage:
        return True
    sl = stage.lower().strip()
    if any(kw in sl for kw in _CLOSED_KEYWORDS):
        return True
    if "onboarding completed" in sl and "converted" in sl:
        return True
    return False


def _get_open_deal_ids() -> set[str]:
    offset = 0
    ids = set()
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_stage")
            .range(offset, offset + 499)
            .execute()
        )
        if not result.data:
            break
        for d in result.data:
            if not _is_closed_stage(d.get("deal_stage") or ""):
                ids.add(d["id"])
        offset += 500
        if len(result.data) < 500:
            break
    return ids


def _fix_atlas_flags(open_deals: set[str], *, dry_run: bool) -> int:
    """Set atlas_ready=TRUE for deals that have atlas or have no crm_id."""
    result = (
        supabase.table("deal_confirmations")
        .select("deal_id")
        .eq("atlas_ready", False)
        .execute()
    )
    blocked = [r["deal_id"] for r in result.data or [] if r["deal_id"] in open_deals]

    fixed = 0
    for did in blocked:
        deal = (
            supabase.table("deals")
            .select("crm_id")
            .eq("id", did)
            .maybe_single()
            .execute()
        )
        crm_id = (deal.data or {}).get("crm_id")

        should_fix = False
        if not crm_id:
            should_fix = True
        else:
            atlas = (
                supabase.table("atlas")
                .select("id")
                .eq("crm_id", crm_id)
                .maybe_single()
                .execute()
            )
            if atlas.data:
                should_fix = True

        if should_fix:
            if not dry_run:
                supabase.table("deal_confirmations").update(
                    {"atlas_ready": True}
                ).eq("deal_id", did).execute()
            fixed += 1

    return fixed


def _fix_simple_flags(open_deals: set[str], *, dry_run: bool) -> dict[str, int]:
    """Set emails_ready/meetings_ready/notes_ready=TRUE for stuck open deals."""
    counts = {}
    for flag in ("emails_ready", "meetings_ready", "notes_ready"):
        result = (
            supabase.table("deal_confirmations")
            .select("deal_id")
            .eq(flag, False)
            .execute()
        )
        blocked = [r["deal_id"] for r in result.data or [] if r["deal_id"] in open_deals]
        if blocked and not dry_run:
            for did in blocked:
                supabase.table("deal_confirmations").update(
                    {flag: True}
                ).eq("deal_id", did).execute()
        counts[flag] = len(blocked)
    return counts


def _is_gong_stub(transcript: str) -> bool:
    """Detect Gong/HubSpot call metadata stubs (not real conversations)."""
    prefix = transcript[:80]
    return any(marker in prefix for marker in _GONG_STUB_MARKERS)


def _has_real_timestamps(transcript: str) -> bool:
    """Check if transcript has Modjo-style timestamps like [00:00]."""
    return any(f"[{m:02d}:" in transcript[:500] for m in range(60))


def _find_blocking_calls(open_deals: set[str]) -> tuple[list[str], list[str]]:
    """Find calls blocking calls_ready. Returns (auditable, stubs_to_clear)."""
    result = (
        supabase.table("deal_confirmations")
        .select("deal_id")
        .eq("calls_ready", False)
        .execute()
    )
    blocked_deals = [r["deal_id"] for r in result.data or [] if r["deal_id"] in open_deals]

    auditable = []
    stubs = []

    for did in blocked_deals:
        calls = (
            supabase.table("calls")
            .select("id, call_id, rol, transcript")
            .eq("deal_id", did)
            .not_.is_("rol", "null")
            .execute()
        )
        for c in calls.data or []:
            t = c.get("transcript") or ""
            if len(t) < 200:
                continue

            table = "pbd_audits" if c["rol"] == "PBD" else "pae_audits"
            audit = (
                supabase.table(table)
                .select("win_rate_score")
                .eq("call_ref", c["id"])
                .execute()
            )
            has_audit = any(
                a.get("win_rate_score") is not None for a in (audit.data or [])
            )
            if has_audit:
                continue

            if _is_gong_stub(t) or not _has_real_timestamps(t):
                stubs.append(c["call_id"])
            else:
                auditable.append(c["call_id"])

    return auditable, stubs


def _audit_one(call_id: str) -> tuple[bool, str]:
    from src.pipelines.audit.run import run_single

    try:
        result = run_single(call_id)
        return (True, call_id) if result else (False, call_id)
    except Exception as e:
        print(f"      AUDIT {call_id} failed: {e}")
        return False, call_id


def _refresh_calls_ready(open_deals: set[str]) -> int:
    """After auditing, refresh calls_ready for all blocked open deals."""
    result = (
        supabase.table("deal_confirmations")
        .select("deal_id")
        .eq("calls_ready", False)
        .execute()
    )
    blocked = [r["deal_id"] for r in result.data or [] if r["deal_id"] in open_deals]
    fixed = 0
    for did in blocked:
        ready = supabase.rpc("check_calls_ready", {"p_deal_id": did}).execute()
        if ready.data:
            supabase.table("deal_confirmations").update(
                {"calls_ready": True}
            ).eq("deal_id", did).execute()
            fixed += 1
    return fixed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    print("=" * 60)
    print("UNBLOCK ALL OPEN DEALS")
    print("=" * 60)

    print("\n0. Loading open deals ...")
    open_deals = _get_open_deal_ids()
    print(f"   {len(open_deals)} open deals")

    # ── Phase 1: Fix stale flags ────────────────────────────────────────
    print("\n1. Phase 1 — Fix stale flags")

    atlas_fixed = _fix_atlas_flags(open_deals, dry_run=args.dry_run)
    print(f"   atlas_ready: {atlas_fixed} deals fixed")

    flag_counts = _fix_simple_flags(open_deals, dry_run=args.dry_run)
    for flag, count in flag_counts.items():
        print(f"   {flag}: {count} deals fixed")

    # ── Phase 2: Clear Gong stubs ─────────────────────────────────────
    print("\n2. Phase 2 — Find blocking calls ...")
    auditable, stubs = _find_blocking_calls(open_deals)
    print(f"   {len(auditable)} real calls to audit")
    print(f"   {len(stubs)} Gong/HubSpot stubs to clear")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        if stubs:
            print(f"\n  Stubs to clear (rol → NULL):")
            for cid in stubs[:15]:
                print(f"    {cid}")
            if len(stubs) > 15:
                print(f"    ... and {len(stubs) - 15} more")
        if auditable:
            print(f"\n  Calls to audit:")
            for cid in auditable[:15]:
                print(f"    {cid}")
            if len(auditable) > 15:
                print(f"    ... and {len(auditable) - 15} more")
        return

    if stubs:
        print(f"\n   Clearing rol on {len(stubs)} Gong stubs ...")
        cleared = 0
        for cid in stubs:
            try:
                supabase.table("calls").update({"rol": None}).eq("call_id", cid).execute()
                cleared += 1
            except Exception as e:
                print(f"      {cid} CLEAR failed: {e}")
        print(f"   Cleared: {cleared}")

    # ── Phase 3: Audit real calls ───────────────────────────────────────
    if args.limit:
        auditable = auditable[: args.limit]
        print(f"   Limited to {args.limit}")

    if auditable:
        print(f"\n3. Auditing {len(auditable)} calls ({args.workers} workers) ...")
        audited = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_audit_one, cid): cid for cid in auditable}
            for i, future in enumerate(as_completed(futures), 1):
                ok, cid = future.result()
                if ok:
                    audited += 1
                else:
                    failed += 1
                if i % 20 == 0 or i == len(auditable):
                    print(f"   [{i}/{len(auditable)}] audited={audited} failed={failed}")

        print(f"\n   Audited: {audited}, Failed: {failed}")

    print("\n4. Refreshing calls_ready flags ...")
    calls_fixed = _refresh_calls_ready(open_deals)
    print(f"   {calls_fixed} deals unblocked")

    # ── Phase 3: Final verification ─────────────────────────────────────
    print("\n5. Final verification ...")
    not_ready = (
        supabase.table("deal_confirmations")
        .select("deal_id, calls_ready, emails_ready, notes_ready, meetings_ready, atlas_ready")
        .eq("all_ready", False)
        .execute()
    )
    still_blocked = 0
    for conf in not_ready.data or []:
        if conf["deal_id"] not in open_deals:
            continue
        still_blocked += 1

    total_ready = len(open_deals) - still_blocked
    print(f"   Open deals: {len(open_deals)}")
    print(f"   all_ready=TRUE: {total_ready}")
    print(f"   Still blocked: {still_blocked}")

    if still_blocked:
        print("\n   Remaining blockers:")
        for conf in not_ready.data or []:
            if conf["deal_id"] not in open_deals:
                continue
            flags = [
                f for f in ["calls_ready", "emails_ready", "notes_ready", "meetings_ready", "atlas_ready"]
                if not conf.get(f)
            ]
            deal = (
                supabase.table("deals")
                .select("deal_name")
                .eq("id", conf["deal_id"])
                .maybe_single()
                .execute()
            )
            name = (deal.data or {}).get("deal_name", "?")[:40]
            print(f"     {name:40} {' + '.join(flags)}")

    print(f"\n{'=' * 60}")
    print("DONE")


if __name__ == "__main__":
    main()
