"""
PAE Follow-Up: orchestrator.

Triggered after front_deal_snapshot is generated for a deal with
pae_followup_pending = true. Routes to the correct strategy based on
deal stage (active / stalled / closed) and Claude-classified subtype.

Flow:
  1. Load full context (call, deal, audit, front_deals, atlas)
  2. Classify → strategy + subtype
  3. Route to strategy → generate brief + PDF
  4. Send to Slack (PAE channel for active/stalled, TL channel for closed)
"""

import os

from src.pipelines.pae_demo_prep.run import PAE_CHANNELS
from src.pipelines.pae_followup.classifier import classify
from src.pipelines.pae_followup.context import load_full_context
from src.pipelines.pae_followup.slack import send_report
from src.pipelines.pae_followup.strategies import run_strategy

TL_CHANNEL = os.environ.get("TL_CHANNEL", "")


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
    subtype = classification["subtype"]
    is_won = classification.get("is_won", False)

    print(f"   Strategy: {strategy}")
    print(f"   Subtype: {subtype}")
    print(f"   Reasoning: {classification.get('reasoning', '')}")

    data["classification"] = classification

    print(f"3. Running strategy: {strategy}/{subtype} ...")
    pdf_bytes, brief = run_strategy(
        strategy=strategy,
        subtype=subtype,
        data=data,
    )
    print(f"   PDF: {len(pdf_bytes)} bytes")

    print("4. Sending to Slack ...")
    if strategy == "closed":
        channel = os.environ.get("PAE_CHANNEL_OVERRIDE") or TL_CHANNEL
        report_label = "Win Report" if is_won else "Loss Report"
    else:
        channel = os.environ.get("PAE_CHANNEL_OVERRIDE") or PAE_CHANNELS.get(pae_name)
        report_label = f"Follow-up ({subtype})" if strategy == "active" else f"Re-engagement ({subtype})"

    if not channel:
        print(f"   No Slack channel for PAE '{pae_name}' / strategy '{strategy}' — skipping")
        return

    send_report(
        pdf_bytes=pdf_bytes,
        company=company,
        demo_date_short=data["demo_date_short"],
        amount_str=data["amount_str"],
        partner=data["partner"],
        contact=data["contact"],
        channel=channel,
        report_label=report_label,
        strategy=strategy,
        subtype=subtype,
        pae_name=pae_name,
    )

    print(f"   Done: {strategy}/{subtype} for {company} → {channel}")
