"""
PAE Follow-Up: generate a post-demo follow-up PDF and send it to Slack.

Triggered when a PAE Demo call is audited. Reads deal context (which
already includes the demo audit), calls Claude to generate a structured
follow-up plan, renders PDF, and sends to the PAE's Slack channel.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.pae_demo_prep.run import PAE_CHANNELS
from src.pipelines.pae_followup.pdf import generate_pdf
from src.pipelines.pae_followup.slack import send_followup_brief

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_MESES_CORTO = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "pae_followup.txt").read_text(encoding="utf-8")


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _extract_contact(deal_data: dict) -> dict:
    contacts_info = deal_data.get("contacts_info") or ""
    if not contacts_info:
        return {"name": "?", "jobtitle": "", "email": "", "phone": ""}
    first_line = contacts_info.split("\n")[0]
    parts = [p.strip() for p in first_line.split("|")]
    return {
        "name": parts[0] if len(parts) > 0 else "?",
        "jobtitle": parts[1] if len(parts) > 1 else "",
        "email": parts[2] if len(parts) > 2 else "",
        "phone": parts[3] if len(parts) > 3 else "",
    }


def _partner_name(deal_data: dict) -> str:
    name = deal_data.get("deal_name") or ""
    if "from " in name:
        return name.split("from ")[-1].strip()
    return "Santander"


def _demo_date_short(fecha: str) -> str:
    if not fecha:
        return "—"
    try:
        dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
        return f"{dt.day} {_MESES_CORTO[dt.month]}"
    except Exception:
        return fecha[:10]


def _demo_datetime_label(fecha: str) -> str:
    if not fecha:
        return "Demo"
    try:
        dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
        madrid = dt.astimezone(ZoneInfo("Europe/Madrid"))
        return f"Demo · {madrid.day} {_MESES_CORTO[madrid.month]}, {madrid.strftime('%H:%M')}"
    except Exception:
        return f"Demo · {fecha[:10]}"


def _followup_datetime_label(fecha: str) -> str:
    if not fecha:
        return "Email follow-up"
    try:
        dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
        fu = dt + timedelta(days=2)
        return f"Email follow-up · {fu.day} {_MESES_CORTO[fu.month]} 09:00"
    except Exception:
        return "Email follow-up"


def run(call_ref: str):
    print(f"1. Loading call {call_ref} ...")
    call = (
        supabase.table("calls")
        .select("*")
        .eq("id", call_ref)
        .maybe_single()
        .execute()
    )
    if not call.data:
        print(f"   Call not found — skipping")
        return

    call_data = call.data
    deal_id = call_data.get("deal_id")
    if not deal_id:
        print(f"   No deal_id on call — skipping")
        return

    print(f"2. Loading deal {deal_id} ...")
    deal = (
        supabase.table("deals")
        .select("*, atlas:atlas_id(company_name)")
        .eq("id", deal_id)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        print(f"   Deal not found — skipping")
        return

    deal_data = deal.data
    deal_context = deal_data.get("deal_context") or ""
    if not deal_context.strip():
        print(f"   deal_context empty — skipping (no context to analyze)")
        return

    pae_name = deal_data.get("pae") or call_data.get("owner_nombre") or ""
    channel = os.environ.get("PAE_CHANNEL_OVERRIDE") or PAE_CHANNELS.get(pae_name)
    if not channel:
        print(f"   No Slack channel for PAE '{pae_name}' — skipping")
        return

    raw_company = (deal_data.get("atlas") or {}).get("company_name") or deal_data.get("deal_name") or "?"
    company = raw_company.split(" - from ")[0].split(" from ")[0].strip() if " from " in raw_company else raw_company

    contact = _extract_contact(deal_data)
    fecha = call_data.get("fecha") or ""
    demo_date_short = _demo_date_short(fecha)
    demo_datetime = _demo_datetime_label(fecha)
    followup_datetime = _followup_datetime_label(fecha)
    amount = deal_data.get("amount")
    amount_str = f"€{float(amount):.0f} MRR" if amount else "MRR desconocido"
    partner = _partner_name(deal_data)

    print(f"   Company: {company}")
    print(f"   PAE: {pae_name} → {channel}")
    print(f"   Demo: {demo_datetime}")

    print("3. Calling Claude ...")
    system_prompt = _load_system_prompt()

    context_block = "\n".join([
        f"## DEAL — {deal_data.get('deal_name', '?')}",
        f"Amount: {deal_data.get('amount') or '?'} | Stage: {deal_data.get('deal_stage', '?')}",
        f"PBD: {deal_data.get('pbd', '?')} | PAE: {pae_name}",
        f"Contacts: {deal_data.get('contacts_info') or 'N/A'}",
        "",
        deal_context,
    ])

    user_prompt = (
        f"[PRE-COMPUTED — use exactly]\n"
        f"company: {company}\n"
        f"demo_datetime: {demo_datetime}\n"
        f"followup_datetime: {followup_datetime}\n"
        f"mrr: {amount_str}\n"
        f"partner: {partner}\n"
        f"pae: {pae_name}\n"
        f"prospect.name: {contact['name']}\n"
        f"prospect.role: {contact['jobtitle']}\n"
        f"prospect.email: {contact['email']}\n"
        f"prospect.phone: {contact['phone']}\n"
        f"\nDEAL CONTEXT:\n{context_block}"
    )
    raw_response = analyze(system_prompt, user_prompt, max_tokens=4000)
    brief = _parse_response(raw_response)

    print("4. Generating PDF ...")
    pdf_bytes = generate_pdf(
        brief=brief,
        company=company,
        demo_datetime=demo_datetime,
        followup_datetime=followup_datetime,
        demo_date_short=demo_date_short,
        amount_str=amount_str,
        partner=partner,
        contact=contact,
        pae_name=pae_name,
    )
    print(f"   PDF: {len(pdf_bytes)} bytes")

    print("5. Sending to Slack ...")
    send_followup_brief(
        pdf_bytes=pdf_bytes,
        company=company,
        demo_date_short=demo_date_short,
        amount_str=amount_str,
        partner=partner,
        contact=contact,
        channel=channel,
    )

    print(f"   Done: follow-up for {company} → {pae_name}")
