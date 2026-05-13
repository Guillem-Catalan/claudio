"""
Generate close report (won or lost) for the TL.
"""

import json
import re
from pathlib import Path

from src.integrations.claude import analyze

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "pae_followup" / "closed"


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def generate_brief(subtype: str, data: dict) -> dict:
    prompt_file = _PROMPTS_DIR / f"{subtype}.txt"
    if not prompt_file.exists():
        prompt_file = _PROMPTS_DIR / "lost_other.txt"

    system_prompt = prompt_file.read_text(encoding="utf-8")

    deal = data["deal"]
    company = data["company"]
    pae_name = data["pae_name"]
    contact = data["contact"]
    amount_str = data["amount_str"]
    partner = data["partner"]
    demo_datetime = data["demo_datetime"]
    context_text = data["context_text"]

    user_prompt = (
        f"[PRE-COMPUTED — use exactly]\n"
        f"company: {company}\n"
        f"demo_datetime: {demo_datetime}\n"
        f"mrr: {amount_str}\n"
        f"partner: {partner}\n"
        f"pae: {pae_name}\n"
        f"contact_name: {contact.get('name', '?')}\n"
        f"deal_stage: {deal.get('deal_stage', '?')}\n"
        f"subtype: {subtype}\n"
    )

    front_snapshot = data.get("front_deals_snapshot") or {}
    if front_snapshot:
        user_prompt += "\nFRONT DEALS SNAPSHOT:\n"
        for key in (
            "deal_summary", "objections", "buyer_signals", "live_blockers",
            "improvements", "deal_strengths", "next_step", "close_probability",
            "claudio_forecast", "m_accumulate", "e_accumulate", "dc_accumulate",
            "dp_accumulate", "i_accumulate", "c_accumulate",
        ):
            val = front_snapshot.get(key)
            if val:
                user_prompt += f"  {key}: {val}\n"

    user_prompt += f"\nDEAL CONTEXT:\n{context_text}"

    raw = analyze(system_prompt, user_prompt, max_tokens=6000)
    return _parse_response(raw)
