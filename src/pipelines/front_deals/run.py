"""
Generate a front_deal snapshot for a single deal.
Reads deal_context (pre-built: atlas + emails + notes + audit results),
deal metadata, and previous snapshot → calls Claude → upserts snapshot.
Triggered by deal_confirmations when all readiness flags are TRUE.
"""

import json
import re
from datetime import date
from pathlib import Path

from src.db.client import supabase
from src.integrations.claude import analyze

_ROOT = Path(__file__).resolve().parent.parent.parent
_LANG_VOCAB = (_ROOT / "prompts/lang_es_startup.txt").read_text()
_BASE_TPL = (_ROOT / "prompts/front_deals/base.txt").read_text()
_OUTPUT_SPEC = (_ROOT / "prompts/front_deals/output_spec.txt").read_text()

SYSTEM_PROMPT = _BASE_TPL.replace("{LANG_ES_STARTUP}", _LANG_VOCAB)
TODAY = date.today().isoformat()


def _to_str(val) -> str:
    if isinstance(val, list):
        return "\n".join(
            f"• {item}" if not str(item).startswith("•") else str(item)
            for item in val
        )
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val) if val is not None else ""


def _build_user_prompt(deal: dict, deal_context: str, prev: dict | None) -> str:
    lines = [
        "=== CAPA 2: CONTEXTO DEL DEAL ===",
        "",
        "DATOS DEL DEAL",
        f"- Deal_Name: {deal.get('deal_name') or '?'}",
        f"- Deal_id: {deal.get('deal_id') or '?'}",
        f"- crm_id: {deal.get('crm_id') or ''}",
        f"- Stage: {deal.get('deal_stage') or '?'}",
        f"- MRR: {deal.get('amount') or '?'}€",
        f"- deal_age: {deal.get('deal_age_days') or '?'} días",
        f"- HS_forecast_category: {deal.get('forecast_category') or '?'}",
        f"- PBD: {deal.get('pbd') or 'Ninguno'}",
        f"- PAE: {deal.get('pae') or 'Ninguno'}",
        "",
        "HISTORIAL COMPLETO DEL DEAL",
        "",
    ]

    if deal_context.strip():
        lines.append(deal_context)
    else:
        lines.append("(Sin interacciones registradas)")

    if prev:
        lines += [
            "",
            f"SNAPSHOT ANTERIOR ({prev.get('snapshot_date', '?')})",
        ]
        for field in [
            "deal_summary", "m_score", "e_score", "dc_score",
            "dp_score", "i_score", "c_score", "live_blockers", "next_step",
        ]:
            val = prev.get(field)
            if val is not None and val != "":
                lines.append(f"{field}: {val}")
    else:
        lines.append("")
        lines.append("SNAPSHOT ANTERIOR: No existe. Es el primer análisis de este deal.")

    lines += ["", _OUTPUT_SPEC]
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def run(deal_uuid: str, hs_deal_id: str):
    print(f"1. Reading deal {deal_uuid} ...")
    deal = (
        supabase.table("deals")
        .select("*")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        print(f"   Deal {deal_uuid} not found — skipping.")
        return

    d = deal.data
    deal_context = d.get("deal_context") or ""

    if not deal_context.strip():
        print("   No deal_context — skipping.")
        return

    print(f"   {d.get('deal_name')} | stage={d.get('deal_stage')} | context={len(deal_context)} chars")

    print("2. Fetching previous snapshot ...")
    prev_result = (
        supabase.table("front_deal_snapshots")
        .select("*")
        .eq("hs_deal_id", hs_deal_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    prev = prev_result.data if prev_result.data else None
    if prev:
        print(f"   Previous snapshot: {prev.get('snapshot_date')}")
    else:
        print("   No previous snapshot — first analysis.")

    user_prompt = _build_user_prompt(d, deal_context, prev)
    print(f"3. Calling Claude ({len(user_prompt)} chars) ...")
    response_text = analyze(SYSTEM_PROMPT, user_prompt)

    print("4. Parsing response ...")
    claude_out = _parse_response(response_text)
    print(f"   M={claude_out.get('M_score')} E={claude_out.get('E_score')} "
          f"DC={claude_out.get('DC_score')} DP={claude_out.get('DP_score')} "
          f"I={claude_out.get('I_score')} C={claude_out.get('C_score')}")

    try:
        mrr = float(d.get("amount")) if d.get("amount") is not None else None
    except (TypeError, ValueError):
        mrr = None

    snapshot = {
        "deal_id": deal_uuid,
        "hs_deal_id": hs_deal_id,
        "snapshot_date": TODAY,
        "deal_name": d.get("deal_name") or "",
        "crm_id": d.get("crm_id") or "",
        "deal_age": d.get("deal_age_days"),
        "stage": d.get("deal_stage") or "",
        "mrr": mrr,
        "hs_forecast_category": d.get("forecast_category") or "",
        "pbd": _to_str(claude_out.get("PBD")),
        "pae": _to_str(claude_out.get("PAE")),
        "deal_summary": _to_str(claude_out.get("Deal_Summary")),
        "m_accumulate": _to_str(claude_out.get("M_accumulate")),
        "m_score": claude_out.get("M_score"),
        "e_accumulate": _to_str(claude_out.get("E_accumulate")),
        "e_score": claude_out.get("E_score"),
        "dc_accumulate": _to_str(claude_out.get("DC_accumulate")),
        "dc_score": claude_out.get("DC_score"),
        "dp_accumulate": _to_str(claude_out.get("DP_accumulate")),
        "dp_score": claude_out.get("DP_score"),
        "i_accumulate": _to_str(claude_out.get("I_accumulate")),
        "i_score": claude_out.get("I_score"),
        "c_accumulate": _to_str(claude_out.get("C_accumulate")),
        "c_score": claude_out.get("C_score"),
        "objections": _to_str(claude_out.get("objections")),
        "buyer_signals": _to_str(claude_out.get("buyer_signals")),
        "live_blockers": _to_str(claude_out.get("live_blockers")),
        "improvements": _to_str(claude_out.get("improvements")),
        "deal_strengths": _to_str(claude_out.get("deal_strengths")),
        "next_step": _to_str(claude_out.get("next_step")),
    }
    snapshot = {k: v for k, v in snapshot.items() if v is not None and v != ""}

    print("5. Writing snapshot ...")
    supabase.table("front_deal_snapshots").upsert(
        snapshot, on_conflict="hs_deal_id,snapshot_date"
    ).execute()

    print(f"   Done. Snapshot for {d.get('deal_name')} written.")
