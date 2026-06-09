"""Briefing pipeline: generate meeting-adapted briefing and store in Supabase."""

import json
import re

from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.pae_demo_prep.context import build_context
from src.pipelines.briefing.prompt import build_prompt, detect_meeting_type


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _set_status(briefing_id: str, status: str, brief: dict | None = None):
    update = {"status": status}
    if brief is not None:
        update["brief"] = brief
    supabase.table("briefings").update(update).eq("id", briefing_id).execute()


def run(*, briefing_id: str | None = None, deal_uuid: str | None = None, meeting_type: str | None = None):
    if briefing_id:
        row = supabase.table("briefings").select("*").eq("id", briefing_id).maybe_single().execute()
        if not row.data:
            raise ValueError(f"Briefing {briefing_id} not found")
        deal_uuid = deal_uuid or str(row.data["deal_id"])
        meeting_type = meeting_type or row.data["meeting_type"]
        _set_status(briefing_id, "generating")
        print(f"1. Briefing {briefing_id} → generating ({meeting_type})")

    if not deal_uuid:
        raise ValueError("Either briefing_id or deal_uuid is required")

    print(f"2. Building context for deal {deal_uuid} ...")
    deal_data, context = build_context(deal_uuid)

    if not meeting_type:
        meeting_type = detect_meeting_type(deal_data.get("deal_stage"))
        print(f"   Detected meeting type: {meeting_type}")

    if not briefing_id:
        deal_name = deal_data.get("deal_name") or "?"
        row = supabase.table("briefings").insert({
            "deal_id": deal_uuid,
            "deal_name": deal_name,
            "meeting_type": meeting_type,
            "status": "generating",
        }).execute()
        briefing_id = row.data[0]["id"]
        print(f"   Created briefing row {briefing_id}")

    print(f"3. Calling Claude ({meeting_type}) ...")
    system_prompt = build_prompt(meeting_type)
    company = deal_data.get("deal_name") or "?"
    user_prompt = f"Generate briefing for: {company}\nMeeting type: {meeting_type}\n\n{context}"

    try:
        raw_response = analyze(system_prompt, user_prompt, model="claudio-claude-sonnet-4-6")
        brief = _parse_response(raw_response)
    except Exception as e:
        print(f"   ERROR: {e}")
        _set_status(briefing_id, "error")
        raise

    print("4. Saving briefing ...")
    _set_status(briefing_id, "ready", brief)
    print(f"   Done: briefing {briefing_id} ready")
