"""
CLI: generate demo evaluation PDF and send to Slack.

Usage: python -m scripts.demo_report <audit_demo_id>
"""

import argparse
import os

from src.db.client import supabase
from src.pipelines.demo_evaluation.pdf import generate_pdf
from src.pipelines.demo_evaluation.slack import send_demo_report
from src.config import PAE_CHANNELS

SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID") or "C0ATY3V8CN4"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_demo_id")
    args = parser.parse_args()

    print(f"1. Loading audit_demo {args.audit_demo_id} ...")
    resp = (
        supabase.table("audit_demos")
        .select("*")
        .eq("id", args.audit_demo_id)
        .single()
        .execute()
    )
    data = resp.data
    if not data:
        print(f"   Not found: {args.audit_demo_id}")
        return

    company = data.get("company_name") or "?"
    pae = data.get("pae") or data.get("owner_name") or "?"
    partner = data.get("partner") or "?"
    amount = data.get("amount")
    amount_str = f"€{float(amount):,.0f}" if amount else "—"

    print(f"   Company: {company}, PAE: {pae}, Partner: {partner}")

    print("2. Generating PDF ...")
    pdf_bytes = generate_pdf(data)
    print(f"   PDF: {len(pdf_bytes)} bytes")

    channel = PAE_CHANNELS.get(pae) or SLACK_CHANNEL_ID
    print(f"3. Sending to Slack ({channel}) ...")
    send_demo_report(
        pdf_bytes=pdf_bytes,
        company=company,
        pae=pae,
        partner=partner,
        amount_str=amount_str,
        channel=channel,
    )

    supabase.table("audit_demos").update({"pdf_generated": True}).eq("id", args.audit_demo_id).execute()
    print("   Done.")


if __name__ == "__main__":
    main()
