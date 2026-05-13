"""
PAE Follow-Up: generate a post-demo follow-up PDF and send it to Slack.

Triggered when a PAE Demo call is audited. Reads deal context (which
already includes the demo audit), calls Claude to generate a structured
follow-up plan, renders PDF, and sends to the PAE's Slack channel.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.pae_demo_prep.run import PAE_CHANNELS
from src.pipelines.pae_followup.context import build_context
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

    print(f"2. Building context for deal {deal_id} ...")
    deal_data, context_text = build_context(deal_id)

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
    amount = deal_data.get("amount")
    amount_str = f"€{float(amount):.0f} MRR" if amount else "MRR desconocido"
    partner = _partner_name(deal_data)

    print(f"   Company: {company}")
    print(f"   PAE: {pae_name} → {channel}")
    print(f"   Demo: {demo_datetime}")

    print("3. Calling Claude ...")
    system_prompt = _load_system_prompt()

    user_prompt = (
        f"[PRE-COMPUTED — use exactly]\n"
        f"company: {company}\n"
        f"demo_datetime: {demo_datetime}\n"
        f"mrr: {amount_str}\n"
        f"partner: {partner}\n"
        f"pae: {pae_name}\n"
        f"\nDEAL CONTEXT:\n{context_text}"
    )
    raw_response = analyze(system_prompt, user_prompt, max_tokens=8000)
    brief = _parse_response(raw_response)

    next_step = brief.get("next_step") or "pendiente de definir"
    step_type = brief.get("next_step_type", "email")
    print(f"   Next step: {next_step} (type={step_type})")

    print("4. Generating PDF ...")
    pdf_bytes = generate_pdf(
        brief=brief,
        company=company,
        demo_datetime=demo_datetime,
        next_step=next_step,
        amount_str=amount_str,
        partner=partner,
        pae_name=pae_name,
        contact=contact,
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
