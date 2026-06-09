"""
Demo Evaluation: generate a demo-quality snapshot after a PAE Demo audit.

Triggered from audit/run.py when a call with tag "Partners - PAE Demo" is audited.
Uses the same JSON structure as front_deal_snapshots but with demo-coaching rubrics.
"""

import json
import re
from pathlib import Path

from src.db.client import supabase
from src.integrations.claude import analyze
from src.config import get_subteam

_ROOT = Path(__file__).resolve().parent.parent.parent
_LANG_VOCAB = (_ROOT / "prompts/lang_es_startup.txt").read_text()
_OUTPUT_SPEC = (_ROOT / "prompts/demo_evaluation/output_spec_first_demo.txt").read_text()

SYSTEM_PROMPT = (
    "Eres un coach de demos de ventas B2B SaaS. "
    "Recibirás el historial completo de un deal más la transcripción de la demo que acaba de ocurrir. "
    "Tu trabajo es evaluar cómo ejecutó el PAE esta demo: qué hizo bien, qué debería mejorar, "
    "y qué logró extraer del prospect en esta interacción concreta.\n\n"
    + _LANG_VOCAB
)


def _to_str(val) -> str:
    if isinstance(val, list):
        return "\n".join(
            f"• {item}" if not str(item).startswith("•") else str(item)
            for item in val
        )
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val) if val is not None else ""


def _parse_response(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _resolve_company_name(crm_id: str | None) -> str:
    if not crm_id:
        return "?"
    try:
        result = (
            supabase.table("atlas")
            .select("company_name")
            .eq("crm_id", crm_id)
            .maybe_single()
            .execute()
        )
        return result.data["company_name"] if result.data else "?"
    except Exception:
        return "?"


def _format_date(val) -> str:
    return str(val)[:10] if val else "—"


def _build_user_prompt(call: dict, deal: dict, deal_context: str) -> str:
    amount = deal.get("amount")
    amount_str = f"{float(amount):,.0f}€" if amount is not None else "?"

    lines = [
        "=== CONTEXTO DEL DEAL ===",
        "",
        "DATOS DEL DEAL",
        f"- Deal_Name: {deal.get('deal_name') or '?'}",
        f"- Deal_id: {deal.get('deal_id') or '?'}",
        f"- Stage: {deal.get('deal_stage') or '?'}",
        f"- Forecast_Category: {deal.get('forecast_category') or '?'}",
        f"- MRR: {amount_str}",
        f"- Close_Date: {_format_date(deal.get('close_date'))}",
        f"- Created: {_format_date(deal.get('createdate'))}",
        f"- Deal_Age_Days: {deal.get('deal_age_days') or '?'}",
        f"- PBD: {deal.get('pbd') or 'Ninguno'}",
        f"- PAE: {deal.get('pae') or 'Ninguno'}",
        f"- Contacts_Info: {deal.get('contacts_info') or '—'}",
        f"- Rep_Next_Step: {deal.get('rep_next_step') or '—'}",
        f"- Rep_Probability: {deal.get('rep_probability') or '?'}",
        f"- Emails: {deal.get('numero_de_emails') or 0}, Calls: {deal.get('numero_de_calls') or 0}, Notes: {deal.get('numero_de_notas') or 0}",
        f"- Last_Contacted: {_format_date(deal.get('last_contacted_hs'))}",
        "",
        "HISTORIAL COMPLETO DEL DEAL (incluye calls PBD, emails, audits previos, handover)",
        "",
    ]

    if deal_context.strip():
        lines.append(deal_context)
    else:
        lines.append("(Sin interacciones registradas previas)")

    lines += [
        "",
        "=== DEMO QUE SE EVALÚA ===",
        "",
        f"- Rep: {call.get('owner_nombre', '?')} ({call.get('owner_email', '?')})",
        f"- Fecha: {(call.get('fecha') or '?')[:10]}",
        f"- Duración: {round((call.get('duracion_segundos') or 0) / 60)} min",
        "",
        "TRANSCRIPT DE LA DEMO",
        "",
        call.get("transcript") or "(sin transcript)",
        "",
        _OUTPUT_SPEC,
    ]
    return "\n".join(lines)


def run(call: dict, pae_audit: dict, deal_context: str):
    print(f"  [demo_eval] Starting for call {call.get('call_id')} ...")

    deal_uuid = call.get("deal_id")
    deal_data = {}
    if deal_uuid:
        resp = (
            supabase.table("deals")
            .select("*")
            .eq("id", deal_uuid)
            .limit(1)
            .execute()
        )
        deal_data = resp.data[0] if resp.data else {}

    if not deal_data and call.get("hs_deal_id"):
        resp = (
            supabase.table("deals")
            .select("*")
            .eq("deal_id", call["hs_deal_id"])
            .limit(1)
            .execute()
        )
        if resp.data:
            deal_data = resp.data[0]
            deal_uuid = deal_data["id"]

    company_name = _resolve_company_name(deal_data.get("crm_id") or call.get("crm_id"))
    partner = get_subteam(call.get("owner_email") or "") or ""

    user_prompt = _build_user_prompt(call, deal_data, deal_context)
    print(f"  [demo_eval] Calling Claude ({len(user_prompt)} chars) ...")
    response_text = analyze(SYSTEM_PROMPT, user_prompt, model="claudio-claude-sonnet-4-6")

    print(f"  [demo_eval] Parsing response ...")
    claude_out = _parse_response(response_text)
    print(f"  [demo_eval] M={claude_out.get('M_score')} E={claude_out.get('E_score')} "
          f"DC={claude_out.get('DC_score')} DP={claude_out.get('DP_score')} "
          f"I={claude_out.get('I_score')} C={claude_out.get('C_score')}")

    pae_audit_id = pae_audit.get("id")
    if not pae_audit_id:
        existing = (
            supabase.table("pae_audits")
            .select("id")
            .eq("call_ref", call["id"])
            .limit(1)
            .execute()
        )
        pae_audit_id = existing.data[0]["id"] if existing.data else None

    try:
        mrr = float(deal_data.get("amount")) if deal_data.get("amount") is not None else None
    except (TypeError, ValueError):
        mrr = None

    row = {
        "call_ref": call["id"],
        "call_id": call["call_id"],
        "deal_ref": deal_uuid,
        "hs_deal_id": call.get("hs_deal_id") or deal_data.get("deal_id"),
        "pae_audit_ref": pae_audit_id,
        "owner_name": call.get("owner_nombre"),
        "owner_email": call.get("owner_email"),
        "demo_date": call.get("fecha"),
        "company_name": company_name,
        "partner": partner,
        "deal_name": deal_data.get("deal_name"),
        "deal_stage": deal_data.get("deal_stage"),
        "amount": mrr,
        "pbd": deal_data.get("pbd"),
        "pae": deal_data.get("pae"),
        "demo_summary": _to_str(claude_out.get("Demo_Summary")),
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
    row = {k: v for k, v in row.items() if v is not None and v != ""}

    print(f"  [demo_eval] Writing to audit_demos ...")
    supabase.table("audit_demos").upsert(row, on_conflict="call_ref").execute()
    print(f"  [demo_eval] Done.")
