"""
Generate a PBD (BANT) snapshot for a single deal.
Reads deal_context + last pbd_audit BANT → calls Claude → upserts pbd_snapshots.
Only runs for deals in PBD stages (up to and including Demo Booked).
"""

import json
import re
from datetime import date
from pathlib import Path

from src.db.client import supabase
from src.integrations.claude import analyze

_PROMPT = (Path(__file__).resolve().parent.parent.parent / "prompts/pbd_snapshot.txt").read_text()
_MODEL = "claude-sonnet-4-6"

PBD_STAGES = frozenset({
    "Research & Outreach",
    "Pre-qualified",
    "Associating the partner",
    "Engaged",
    "Attempting to contact",
    "Nurturing",
    "New",
    "Demo Booked",
    "New Deals",
    "To reschedule",
    "Opportunity detected",
    "Meeting Booked",
    "Discovery",
    "Sales Nurturing",
    "Client Contacted",
    "Connected - Not Engaged",
    "Long Nurturing",
    "Attempted to contact",
    "Hot Nurturing",
    "Meeting scheduled",
})


def _fetch_previous_bant(deal_uuid: str) -> str | None:
    result = (
        supabase.table("pbd_audits")
        .select(
            "bant_budget_status, bant_budget_evidence,"
            "bant_authority_status, bant_authority_evidence,"
            "bant_need_status, bant_need_evidence,"
            "bant_timing_status, bant_timing_evidence"
        )
        .eq("deal_ref", deal_uuid)
        .not_.is_("bant_budget_status", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    a = result.data[0]
    lines = ["BANT de última auditoría PBD:"]
    for letter, field in [("B", "budget"), ("A", "authority"), ("N", "need"), ("T", "timing")]:
        status = a.get(f"bant_{field}_status") or "?"
        evidence = a.get(f"bant_{field}_evidence") or ""
        lines.append(f"  {letter}: {status} — {evidence}" if evidence else f"  {letter}: {status}")
    return "\n".join(lines)


def _build_user_prompt(deal: dict, deal_context: str, prev_bant: str | None, prev_snapshot: dict | None) -> str:
    lines = [
        "## Deal",
        f"- Nombre: {deal.get('deal_name') or '?'}",
        f"- Stage: {deal.get('deal_stage') or '?'}",
        f"- MRR: {deal.get('amount') or '?'}€",
        f"- PBD: {deal.get('pbd') or 'Ninguno'}",
        f"- PAE: {deal.get('pae') or 'Ninguno'}",
        "",
    ]

    if prev_bant:
        lines += ["## BANT previo (de auditoría PBD)", prev_bant, ""]
    elif prev_snapshot:
        s = prev_snapshot
        lines += [
            f"## BANT previo (snapshot {s.get('snapshot_date', '?')})",
            f"  B: {s.get('bant_b_status') or '?'} — {s.get('bant_b_evidence') or ''}",
            f"  A: {s.get('bant_a_status') or '?'} — {s.get('bant_a_evidence') or ''}",
            f"  N: {s.get('bant_n_status') or '?'} — {s.get('bant_n_evidence') or ''}",
            f"  T: {s.get('bant_t_status') or '?'} — {s.get('bant_t_evidence') or ''}",
            "",
        ]
    else:
        lines += ["## BANT previo", "No hay auditoría PBD ni snapshot previo.", ""]

    lines += ["## Contexto completo del deal", "", deal_context or "(Sin interacciones registradas)"]
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def run(deal_uuid: str, hs_deal_id: str):
    print(f"1. Reading deal {deal_uuid} ...")
    deal = (
        supabase.table("deals")
        .select("*")
        .eq("id", deal_uuid)
        .limit(1)
        .execute()
    )
    if not deal.data:
        print(f"   Deal {deal_uuid} not found — skipping.")
        return

    d = deal.data[0]
    stage = d.get("deal_stage") or ""

    if stage not in PBD_STAGES:
        print(f"   Stage '{stage}' is not a PBD stage — skipping.")
        return

    deal_context = d.get("deal_context") or ""
    if not deal_context.strip():
        print("   No deal_context — skipping.")
        return

    print(f"   {d.get('deal_name')} | stage={stage} | context={len(deal_context)} chars")

    print("2. Fetching previous BANT ...")
    prev_bant = _fetch_previous_bant(deal_uuid)
    if prev_bant:
        print("   Found BANT from pbd_audit.")
    else:
        print("   No pbd_audit BANT.")

    print("3. Fetching previous snapshot ...")
    prev_result = (
        supabase.table("pbd_snapshots")
        .select("*")
        .eq("hs_deal_id", hs_deal_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    prev_snapshot = prev_result.data[0] if prev_result.data else None
    if prev_snapshot:
        print(f"   Previous snapshot: {prev_snapshot.get('snapshot_date')}")
    else:
        print("   No previous snapshot.")

    user_prompt = _build_user_prompt(d, deal_context, prev_bant, prev_snapshot)
    print(f"4. Calling Claude ({len(user_prompt)} chars) ...")
    response_text = analyze(_PROMPT, user_prompt, model=_MODEL)

    print("5. Parsing response ...")
    out = _parse_response(response_text)

    snapshot = {
        "deal_id": deal_uuid,
        "hs_deal_id": hs_deal_id,
        "snapshot_date": date.today().isoformat(),
        "bant_b_status": out.get("bant_b_status"),
        "bant_b_evidence": out.get("bant_b_evidence"),
        "bant_a_status": out.get("bant_a_status"),
        "bant_a_evidence": out.get("bant_a_evidence"),
        "bant_n_status": out.get("bant_n_status"),
        "bant_n_evidence": out.get("bant_n_evidence"),
        "bant_t_status": out.get("bant_t_status"),
        "bant_t_evidence": out.get("bant_t_evidence"),
        "pbd_summary": out.get("pbd_summary"),
    }
    snapshot = {k: v for k, v in snapshot.items() if v is not None}

    print(f"   B={snapshot.get('bant_b_status')} A={snapshot.get('bant_a_status')} "
          f"N={snapshot.get('bant_n_status')} T={snapshot.get('bant_t_status')}")

    print("6. Writing snapshot ...")
    supabase.table("pbd_snapshots").upsert(
        snapshot, on_conflict="hs_deal_id,snapshot_date"
    ).execute()

    print(f"   Done. PBD snapshot for {d.get('deal_name')} written.")
