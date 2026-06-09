"""
Generate a front_deal snapshot for a single deal.
Reads deal_context (pre-built: atlas + emails + notes + audit results),
deal metadata, and previous snapshot → calls Claude → upserts snapshot.

Consolidated pipeline: MEDDIC snapshot + forecast + PBD BANT (if applicable)
in a single workflow run.
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
_FORECAST_BASE = (_ROOT / "prompts/front_forecast/base.txt").read_text()
_FORECAST_OUTPUT_SPEC = (_ROOT / "prompts/front_forecast/output_spec.txt").read_text()
_PBD_PROMPT = (_ROOT / "prompts/pbd_snapshot.txt").read_text()

SYSTEM_PROMPT = _BASE_TPL.replace("{LANG_ES_STARTUP}", _LANG_VOCAB)
TODAY = date.today().isoformat()

_FORECAST_SYSTEM = (
    "You are a sales deal classifier. "
    "Analyze the current deal snapshot and classify: deal-killer presence, "
    "buyer signal strength (bs), and blocker severity (lb). "
    "Do not compute any formula — Python handles the math. "
    "End your response with the JSON object on the last line, with no text after it. "
    '{"deal_killer": <bool>, "deal_killer_value": <int 0-7 or null>, "bs": <float>, "lb": <float>}'
)

PBD_STAGES = frozenset({
    "Research & Outreach", "Pre-qualified", "Associating the partner",
    "Engaged", "Attempting to contact", "Nurturing", "New",
    "Demo Booked", "New Deals", "To reschedule",
    "Opportunity detected", "Meeting Booked", "Discovery",
    "Sales Nurturing", "Client Contacted", "Connected - Not Engaged",
    "Long Nurturing", "Attempted to contact", "Hot Nurturing",
    "Meeting scheduled",
})


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
            "deal_summary", "deal_assessment", "m_score", "e_score", "dc_score",
            "dp_score", "i_score", "c_score", "comp_score", "live_blockers", "next_step",
            "action_signal",
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
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _build_forecast_context(snap: dict, close_date: str) -> str:
    scores = " | ".join(
        f"{k}={snap.get(k.lower(), '?')}"
        for k in ["M_score", "E_score", "DC_score", "DP_score", "I_score", "C_score", "Comp_score"]
    )
    lines = [
        "=== CONTEXTO DEL DEAL ===", "",
        f"Deal_Name: {snap.get('deal_name') or '?'}",
        f"Stage: {snap.get('stage') or '?'}",
        f"deal_age: {snap.get('deal_age') or '?'} días",
        f"Close_date esperada: {close_date}",
        f"MRR: {snap.get('mrr') or '?'}€",
        f"HS_forecast_category: {snap.get('hs_forecast_category') or '?'}",
        "", "=== SNAPSHOT ACTUAL ===", "",
        scores,
        f"buyer_signals: {snap.get('buyer_signals') or 'Ninguna'}",
        f"live_blockers: {snap.get('live_blockers') or 'Ninguno'}",
        f"Deal_Summary: {snap.get('deal_summary') or '-'}",
        f"next_step: {snap.get('next_step') or '-'}",
        f"objections: {snap.get('objections') or 'Ninguna'}",
    ]
    return "\n".join(lines)


def _compute_probability(snap: dict, claude_out: dict) -> int:
    if claude_out.get("deal_killer"):
        val = claude_out.get("deal_killer_value")
        return int(val) if val is not None else 3
    try:
        C = float(snap.get("c_score", 0) or 0)
        E = float(snap.get("e_score", 0) or 0)
        DP = float(snap.get("dp_score", 0) or 0)
        DC = float(snap.get("dc_score", 0) or 0)
        I = float(snap.get("i_score", 0) or 0)
        M = float(snap.get("m_score", 0) or 0)
        Comp = float(snap.get("comp_score", 0) or 0)
    except (TypeError, ValueError):
        return 0
    bs = float(claude_out.get("bs") or 0)
    lb = float(claude_out.get("lb") or 0)
    base = C * 0.12 + E * 0.22 + DP * 0.18 + DC * 0.18 + I * 0.13 + M * 0.05 + Comp * 0.12
    adjusted = max(0.0, min(10.0, base + bs + lb))
    return round(adjusted * 10)


def _run_forecast(snapshot: dict, close_date: str) -> dict:
    context = _build_forecast_context(snapshot, close_date)
    prompt = f"{_FORECAST_BASE}\n\n{context}\n\n{_FORECAST_OUTPUT_SPEC}"
    raw = analyze(_FORECAST_SYSTEM, prompt, max_tokens=2000)
    matches = re.findall(r"\{[^{}]+\}", raw)
    if not matches:
        raise ValueError("no JSON found in forecast response")
    claude_out = json.loads(matches[-1])
    close_probability = _compute_probability(snapshot, claude_out)
    mrr = float(snapshot.get("mrr") or 0)
    claudio_forecast = round((close_probability / 100) * mrr, 2)
    return {
        "close_probability": close_probability,
        "claudio_forecast": claudio_forecast,
    }


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


def _build_pbd_user_prompt(deal: dict, deal_context: str, prev_bant: str | None, prev_snapshot: dict | None) -> str:
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


def _run_pbd_snapshot(deal_uuid: str, hs_deal_id: str, deal: dict, deal_context: str):
    prev_bant = _fetch_previous_bant(deal_uuid)
    if prev_bant:
        print("   Found BANT from pbd_audit.")
    else:
        print("   No pbd_audit BANT.")

    prev_result = (
        supabase.table("pbd_snapshots")
        .select("*")
        .eq("hs_deal_id", hs_deal_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    prev_snapshot = prev_result.data[0] if prev_result.data else None

    user_prompt = _build_pbd_user_prompt(deal, deal_context, prev_bant, prev_snapshot)
    print(f"   Calling Claude for BANT ({len(user_prompt)} chars) ...")
    response_text = analyze(_PBD_PROMPT, user_prompt, model="claudio-claude-sonnet-4-6")

    out = _parse_response(response_text)
    snapshot = {
        "deal_id": deal_uuid,
        "hs_deal_id": hs_deal_id,
        "snapshot_date": TODAY,
        "pbd": deal.get("pbd"),
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

    supabase.table("pbd_snapshots").upsert(
        snapshot, on_conflict="hs_deal_id,snapshot_date"
    ).execute()
    print(f"   PBD snapshot written.")


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
        .execute()
    )
    prev = prev_result.data[0] if prev_result.data else None
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
          f"I={claude_out.get('I_score')} C={claude_out.get('C_score')} "
          f"Comp={claude_out.get('Comp_score')}")

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
        "deal_assessment": _to_str(claude_out.get("Deal_Assessment")),
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
        "comp_accumulate": _to_str(claude_out.get("Comp_accumulate")),
        "comp_score": claude_out.get("Comp_score"),
        "objections": _to_str(claude_out.get("objections")),
        "buyer_signals": _to_str(claude_out.get("buyer_signals")),
        "live_blockers": _to_str(claude_out.get("live_blockers")),
        "improvements": _to_str(claude_out.get("improvements")),
        "deal_strengths": _to_str(claude_out.get("deal_strengths")),
        "next_step": _to_str(claude_out.get("next_step")),
        "action_signal": _to_str(claude_out.get("action_signal")),
    }
    snapshot = {k: v for k, v in snapshot.items() if v is not None and v != ""}

    # ── Inline forecast ──────────────────────────────────────────────
    print("5. Computing forecast ...")
    try:
        close_date = d.get("close_date") or "?"
        forecast_result = _run_forecast(snapshot, close_date)
        snapshot["close_probability"] = forecast_result["close_probability"]
        snapshot["claudio_forecast"] = forecast_result["claudio_forecast"]
        print(f"   → {forecast_result['close_probability']}% / {forecast_result['claudio_forecast']}€")
    except Exception as e:
        print(f"   Forecast failed: {e} — writing snapshot without it")

    print("6. Writing snapshot ...")
    existing = (
        supabase.table("front_deal_snapshots")
        .select("id")
        .eq("hs_deal_id", snapshot["hs_deal_id"])
        .eq("snapshot_date", snapshot["snapshot_date"])
        .limit(1)
        .execute()
    )
    if existing.data:
        supabase.table("front_deal_snapshots").update(snapshot).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("front_deal_snapshots").insert(snapshot).execute()
    print(f"   Snapshot for {d.get('deal_name')} written.")

    # ── Inline PBD snapshot (if deal is in PBD stage) ────────────────
    stage = d.get("deal_stage") or ""
    if stage in PBD_STAGES:
        print(f"7. Generating PBD (BANT) snapshot (stage={stage}) ...")
        try:
            _run_pbd_snapshot(deal_uuid, hs_deal_id, d, deal_context)
        except Exception as e:
            print(f"   PBD snapshot failed: {e}")
    else:
        print(f"7. Skipping PBD snapshot (stage={stage} is not PBD).")

    print(f"   Done.")
