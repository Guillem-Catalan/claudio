"""
Process a single email with Claude: generate summary, type, key_people.
Triggered by: trg_email_inserted on emails table.
"""

import json
import re

from src.db.client import supabase
from src.integrations.claude import analyze

SYSTEM_PROMPT = (
    "You are an assistant that analyzes sales emails. "
    "You always respond with valid JSON only — no prose, no markdown."
)

USER_PROMPT = """\
Analyze this sales email from Factorial (HR SaaS) to a prospect.

Subject: {subject}
From: {from_email}
Direction: {direction}
Body:
{body_clean}

Return this JSON:
{{
  "email_type": "<follow_up|proposal|objection|scheduling|no_show|admin|other>",
  "summary": "<2-3 sentences in Spanish summarizing: what was communicated, any commitments or proposals made, and the next step or open ask>",
  "key_people": "<comma-separated list of names with role/company if identifiable — empty string if none found>"
}}"""


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def run(email_id: str):
    print(f"1. Reading email {email_id} from Supabase ...")
    result = (
        supabase.table("emails")
        .select("id, subject, from_email, direction, body_clean")
        .eq("id", email_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        print(f"   Email {email_id} not found — skipping.")
        return

    email = result.data
    if not email.get("body_clean"):
        print("   Empty body_clean — skipping.")
        return

    print("2. Analyzing with Claude ...")
    prompt = USER_PROMPT.format(
        subject=email.get("subject") or "(no subject)",
        from_email=email.get("from_email") or "",
        direction=email.get("direction") or "",
        body_clean=email["body_clean"],
    )

    raw_response = analyze(SYSTEM_PROMPT, prompt)
    parsed = _parse_response(raw_response)

    email_type = parsed.get("email_type", "other")
    summary = parsed.get("summary", "")
    key_people = parsed.get("key_people", "") or ""

    print("3. Writing results to Supabase ...")
    supabase.table("emails").update({
        "email_summary": summary,
        "email_type": email_type,
        "key_people": key_people,
    }).eq("id", email_id).execute()

    print(f"   Done: type={email_type}, summary={summary[:80]}...")
