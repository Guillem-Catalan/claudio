"""
PAE Demo Prep: generate a demo brief PDF and send it to Slack.

Triggered the day before a scheduled demo. Builds full deal context
from Supabase, calls Claude to generate structured briefing, renders
PDF from HTML template, and sends to the PAE's Slack channel.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.pae_demo_prep.context import build_context
from src.pipelines.pae_demo_prep.pdf import generate_pdf
from src.pipelines.pae_demo_prep.slack import send_demo_brief

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

PAE_CHANNELS = {
    "Alejandro Soto Velasco": "C0B36Q1EX9T",
    "Carlos Sanchez": "C0B33QJLF8B",
    "David Clemente": "C0B33QDE4KD",
    "Jose Donis": "C0B24A51PNE",
    "Joan Lorenzo Galles": "C0B2UMVT5NK",
    "Mireia Serrano": "C0B384853M4",
    "Nerea Urien Meizoso": "C0B2UMRUV2T",
    "Pol Bartolomé": "C0B33Q2T7FV",
    "Roberto Morán": "C0B36RD537X",
    "Xavier Fortuny": "C0B1CNJTPMZ",
}


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "pae_demo_prep.txt").read_text(encoding="utf-8")


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


def _meeting_time(deal_data: dict) -> str:
    raw = deal_data.get("hs_next_meeting_start_time") or ""
    if not raw:
        return "hora por confirmar"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.hour == 0 and dt.minute == 0:
            return "hora por confirmar"
        madrid = dt.astimezone(ZoneInfo("Europe/Madrid"))
        return madrid.strftime("%H:%M %Z")
    except Exception:
        return raw[:16]


def _meeting_date(deal_data: dict) -> str:
    raw = deal_data.get("hs_next_meeting_start_time") or deal_data.get("first_meeting_at") or ""
    if not raw:
        return "fecha por confirmar"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return raw[:10]


def _partner_name(deal_data: dict) -> str:
    atlas = deal_data.get("atlas") or {}
    return atlas.get("partner") or "Santander"


def run(deal_uuid: str):
    print(f"1. Building context for deal {deal_uuid} ...")
    deal_data, context = build_context(deal_uuid)

    pae_name = deal_data.get("pae") or ""
    channel = PAE_CHANNELS.get(pae_name)
    if not channel:
        print(f"   No Slack channel for PAE '{pae_name}' — skipping")
        return

    company = (deal_data.get("atlas") or {}).get("company_name") or deal_data.get("deal_name") or "?"
    contact = _extract_contact(deal_data)
    demo_time = _meeting_time(deal_data)
    demo_date = _meeting_date(deal_data)
    amount = deal_data.get("amount")
    amount_str = f"€{float(amount):.0f} MRR" if amount else "MRR desconocido"
    partner = _partner_name(deal_data)

    print(f"   Company: {company}")
    print(f"   PAE: {pae_name} → {channel}")
    print(f"   Contact: {contact['name']} ({contact['jobtitle']})")
    print(f"   Demo: {demo_date} {demo_time}")

    print("2. Calling Claude ...")
    system_prompt = _load_system_prompt()
    user_prompt = f"Generate demo preparation brief for: {company}\n\n{context}"
    raw_response = analyze(system_prompt, user_prompt)
    brief = _parse_response(raw_response)

    print("3. Generating PDF ...")
    pdf_bytes = generate_pdf(
        brief=brief,
        company=company,
        demo_date=demo_date,
        demo_time=demo_time,
        amount_str=amount_str,
        partner=partner,
        contact=contact,
    )
    print(f"   PDF: {len(pdf_bytes)} bytes")

    print("4. Sending to Slack ...")
    send_demo_brief(
        pdf_bytes=pdf_bytes,
        company=company,
        demo_time=demo_time,
        amount_str=amount_str,
        partner=partner,
        contact=contact,
        channel=channel,
    )

    print(f"   Done: demo brief for {company} → {pae_name}")
