"""
PAE Follow-Up: orchestrator.

Triggered after front_deal_snapshot is generated for a deal with
pae_followup_pending = true.

Flow:
  1. Load full context
  2. Classify → strategy + needs
  3a. CLOSED → TL report (strategies/closed/)
  3b. ACTIVE/STALLED → generate all modules → render → send bundle to PAE
"""

import json
import os
import re
from pathlib import Path

from src.integrations.claude import analyze
from src.config import PAE_CHANNELS
from src.pipelines.pae_followup.classifier import classify
from src.pipelines.pae_followup.context import load_full_context
from src.pipelines.pae_followup.modules import CORE_MODULES, render_modules
from src.pipelines.pae_followup.slack import send_bundle

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "pae_followup"
TL_CHANNEL = os.environ.get("TL_CHANNEL", "")


def _load_generator_prompt() -> str:
    return (_PROMPTS_DIR / "generator.txt").read_text(encoding="utf-8")


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _generate_modules(data: dict, needs: list[str]) -> dict:
    """Single Claude call that generates all requested modules."""
    system_prompt = _load_generator_prompt()

    all_modules = CORE_MODULES + needs
    modules_list = ", ".join(all_modules)

    deal = data["deal"]
    company = data["company"]
    pae_name = data["pae_name"]
    contact = data["contact"]
    amount_str = data["amount_str"]
    partner = data["partner"]
    demo_datetime = data["demo_datetime"]
    context_text = data["context_text"]

    user_prompt = (
        f"MODULES TO GENERATE: {modules_list}\n\n"
        f"[PRE-COMPUTED — use exactly]\n"
        f"company: {company}\n"
        f"demo_datetime: {demo_datetime}\n"
        f"mrr: {amount_str}\n"
        f"partner: {partner}\n"
        f"pae: {pae_name}\n"
        f"contact_name: {contact.get('name', '?')}\n"
        f"contact_email: {contact.get('email', '')}\n"
        f"contact_jobtitle: {contact.get('jobtitle', '')}\n"
        f"deal_stage: {deal.get('deal_stage', '?')}\n"
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

    raw = analyze(system_prompt, user_prompt, max_tokens=12000)
    return _parse_response(raw)


def run(call_ref: str):
    print(f"1. Loading context for call {call_ref} ...")
    data = load_full_context(call_ref)

    company = data["company"]
    pae_name = data["pae_name"]
    deal_stage = data["deal"].get("deal_stage", "?")

    print(f"   Company: {company}")
    print(f"   PAE: {pae_name}")
    print(f"   Stage: {deal_stage}")
    print(f"   Front deals snapshot: {'yes' if data.get('front_deals_snapshot') else 'no'}")

    print("2. Classifying ...")
    classification = classify(data)
    strategy = classification["strategy"]
    needs = classification["needs"]
    is_won = classification.get("is_won", False)

    print(f"   Strategy: {strategy}")
    print(f"   Needs: {needs}")
    print(f"   Reasoning: {classification.get('reasoning', '')}")

    data["classification"] = classification

    if strategy == "closed":
        print("3. Generating TL close report ...")
        from src.pipelines.pae_followup.strategies.closed import run as run_closed
        pdf_bytes, brief = run_closed(
            subtype="won" if is_won else "lost_other",
            data=data,
        )
        channel = os.environ.get("PAE_CHANNEL_OVERRIDE") or TL_CHANNEL
        if not channel:
            print("   No TL channel configured — skipping")
            return

        from src.pipelines.pae_followup.slack import send_report_closed
        label = "Win Report" if is_won else "Loss Report"
        send_report_closed(
            pdf_bytes=pdf_bytes,
            company=company,
            demo_date_short=data["demo_date_short"],
            amount_str=data["amount_str"],
            partner=data["partner"],
            pae_name=pae_name,
            channel=channel,
            report_label=label,
        )
        print(f"   Done: {label} for {company} → {channel}")
        return

    print(f"3. Generating {len(CORE_MODULES) + len(needs)} modules ...")
    brief = _generate_modules(data, needs)

    print("4. Rendering modules ...")
    outputs = render_modules(brief, data, needs)
    print(f"   Rendered {len(outputs)} outputs: {[o['module'] for o in outputs]}")

    print("5. Sending bundle to Slack ...")
    channel = os.environ.get("PAE_CHANNEL_OVERRIDE") or PAE_CHANNELS.get(pae_name)
    if not channel:
        print(f"   No Slack channel for PAE '{pae_name}' — skipping")
        return

    send_bundle(
        outputs=outputs,
        company=company,
        demo_date_short=data["demo_date_short"],
        amount_str=data["amount_str"],
        partner=data["partner"],
        channel=channel,
    )

    print(f"   Done: {len(outputs)} modules for {company} → {pae_name}")
