"""
Weekly TL Report: unified per-PAE run.
Part 1: Weekly activity (meetings evaluated by type)
Part 2: Pipeline review (advanced deals)
"""

import json
import os
import re
import traceback
from datetime import date, timedelta
from pathlib import Path

from src.config import TEAMS, TEAM_LEAD_CHANNELS
from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.weekly_tl_report.prompts import (
    build_activity_synthesis,
    build_pipeline_review,
)
from src.pipelines.weekly_tl_report.pdf import generate_pdf
from src.pipelines.demo_evaluation.slack import send_demo_report, send_no_demos_notice

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "meeting_evaluation"

FIRST_DEMO_STAGES = {
    "Factorial Project Alignment started", "FPA", "Demo Booked",
    "Meeting Booked", "Meeting scheduled", "Product Alignment", "Discovery",
}
CLOSING_STAGES = {
    "Economical Allignment Started", "Pricing and Packaging",
    "Pricing & Packaging", "Contract Sent",
}
ADVANCED_STAGES = {
    "Factorial Project Alignment started", "Product Alignment",
    "MEDDPICC Criteria Validation Started", "Economical Allignment Started",
    "Pricing and Packaging", "Pricing & Packaging", "Contract Sent",
}
MIN_PROBABILITY = 46


def _resolve_pae_name(email: str) -> str:
    resp = (
        supabase.table("calls")
        .select("owner_nombre")
        .eq("owner_email", email)
        .not_.is_("owner_nombre", "null")
        .limit(1)
        .execute()
    )
    if resp.data:
        return resp.data[0]["owner_nombre"]
    return email.split("@")[0].replace(".", " ").title()


def _get_team(pae_email: str) -> str | None:
    for team_name, team in TEAMS.items():
        if pae_email in team.get("pae", set()):
            return team_name
    return None


def _classify_meeting_type(deal_stage: str | None, first_meeting_at: str | None, meeting_date: str | None) -> str:
    if first_meeting_at and meeting_date and first_meeting_at == meeting_date[:10]:
        return "first_demo"
    if deal_stage in FIRST_DEMO_STAGES:
        return "first_demo"
    if deal_stage in CLOSING_STAGES:
        return "closing"
    return "follow_up"


# ── Data fetching ────────────────────────────────────────────────────────


def _fetch_pae_deal_ids(pae_name: str) -> list[str]:
    first_last = pae_name.split()[:2]
    pattern = f"%{'%'.join(first_last)}%" if len(first_last) >= 2 else f"%{pae_name}%"
    resp = supabase.table("deals").select("id").ilike("pae", pattern).execute()
    return [d["id"] for d in (resp.data or [])]


def _fetch_meetings_week(pae_deal_ids: list[str], pae_email: str, week_start: date, week_end: date) -> list[dict]:
    """Fetch all meetings from 3 sources, deduped by deal+day."""
    meetings = []
    seen = set()

    # Source 1: deal_meetings (HubSpot)
    for i in range(0, len(pae_deal_ids), 30):
        batch = pae_deal_ids[i:i + 30]
        resp = (
            supabase.table("deal_meetings")
            .select("deal_id, hs_meeting_id, title, meeting_start, meeting_end, outcome")
            .in_("deal_id", batch)
            .gte("meeting_start", week_start.isoformat())
            .lt("meeting_start", week_end.isoformat())
            .order("meeting_start")
            .execute()
        )
        for m in (resp.data or []):
            if m.get("outcome") not in ("COMPLETED", "NO_SHOW"):
                continue
            key = (m["deal_id"], m["meeting_start"][:10])
            if key not in seen:
                seen.add(key)
                m["source"] = "hubspot"
                meetings.append(m)

    # Source 2: calendar_meetings (Google Calendar, resolved)
    resp = (
        supabase.table("calendar_meetings")
        .select("deal_id, title, meeting_start, meeting_end, pae_name")
        .eq("pae_email", pae_email)
        .eq("resolved", True)
        .not_.is_("deal_id", "null")
        .gte("meeting_start", week_start.isoformat())
        .lt("meeting_start", week_end.isoformat())
        .order("meeting_start")
        .execute()
    )
    for m in (resp.data or []):
        key = (m["deal_id"], m["meeting_start"][:10])
        if key not in seen:
            seen.add(key)
            m["source"] = "calendar"
            m["outcome"] = "COMPLETED"
            meetings.append(m)

    meetings.sort(key=lambda m: m.get("meeting_start", ""))
    return meetings


def _enrich_meetings(meetings: list[dict]) -> list[dict]:
    """Add deal data, snapshot, call/audit info to each meeting."""
    deal_ids = list(set(m["deal_id"] for m in meetings if m.get("deal_id")))
    if not deal_ids:
        return meetings

    deal_map = {}
    snap_map = {}
    for i in range(0, len(deal_ids), 30):
        batch = deal_ids[i:i + 30]
        resp = supabase.table("deals").select(
            "id, deal_name, deal_stage, amount, deal_age_days, pae, pbd, first_meeting_at, deal_context"
        ).in_("id", batch).execute()
        for d in (resp.data or []):
            deal_map[d["id"]] = d

        resp2 = (
            supabase.table("front_deal_snapshots")
            .select("deal_id, close_probability, deal_summary, deal_assessment, buyer_signals, live_blockers, next_step, m_score, e_score, dc_score, dp_score, i_score, c_score")
            .in_("deal_id", batch)
            .order("snapshot_date", desc=True)
            .limit(len(batch) * 2)
            .execute()
        )
        for s in (resp2.data or []):
            if s["deal_id"] not in snap_map:
                snap_map[s["deal_id"]] = s

    # Check which meetings have Modjo calls (audit data)
    call_map = {}
    for i in range(0, len(deal_ids), 30):
        batch = deal_ids[i:i + 30]
        resp = (
            supabase.table("calls")
            .select("id, call_id, deal_id, fecha, transcript, owner_email, owner_nombre, duracion_segundos, tags")
            .in_("deal_id", batch)
            .not_.is_("transcript", "null")
            .order("fecha", desc=True)
            .execute()
        )
        for c in (resp.data or []):
            key = (c["deal_id"], (c.get("fecha") or "")[:10])
            if key not in call_map:
                call_map[key] = c

    audit_map = {}
    call_ids_for_audit = [c["id"] for c in call_map.values()]
    for i in range(0, len(call_ids_for_audit), 30):
        batch = call_ids_for_audit[i:i + 30]
        resp = (
            supabase.table("pae_audits")
            .select("call_ref, win_rate_score, buying_signals, blockers, objections, next_call_objective, deal_context")
            .in_("call_ref", batch)
            .not_.is_("win_rate_score", "null")
            .execute()
        )
        for a in (resp.data or []):
            audit_map[a["call_ref"]] = a

    for m in meetings:
        did = m["deal_id"]
        deal = deal_map.get(did, {})
        snap = snap_map.get(did, {})
        m["deal"] = deal
        m["snap"] = snap
        m["deal_name"] = deal.get("deal_name", "?")
        m["deal_stage"] = deal.get("deal_stage", "?")
        m["amount"] = deal.get("amount")
        m["meeting_type"] = _classify_meeting_type(
            deal.get("deal_stage"),
            deal.get("first_meeting_at"),
            m.get("meeting_start"),
        )

        call_key = (did, (m.get("meeting_start") or "")[:10])
        call = call_map.get(call_key)
        m["has_call"] = call is not None
        m["call"] = call
        if call:
            audit = audit_map.get(call["id"])
            m["has_audit"] = audit is not None
            m["audit"] = audit
        else:
            m["has_audit"] = False
            m["audit"] = None

    return meetings


# ── Meeting evaluation ───────────────────────────────────────────────────


def _load_prompt(meeting_type: str) -> str:
    filename = f"output_spec_{meeting_type}.txt"
    path = PROMPTS_DIR / filename
    return path.read_text()


def _evaluate_meeting(meeting: dict) -> dict | None:
    """Evaluate a single meeting with Claude, using type-specific prompt."""
    deal = meeting.get("deal", {})
    snap = meeting.get("snap", {})
    call = meeting.get("call")
    meeting_type = meeting["meeting_type"]

    output_spec = _load_prompt(meeting_type)

    system_prompt = (
        "Eres un coach de ventas B2B SaaS especializado en evaluar reuniones individuales. "
        "Tu trabajo es evaluar la CALIDAD DE EJECUCIÓN de esta reunión específica, "
        "no el estado general del deal. Contexto: Factorial vende HR software "
        "a través de partners (Santander, Telefónica, TIM).\n\n"
        "Responde ÚNICAMENTE con un JSON válido, sin markdown, sin prose."
    )

    context_parts = [
        f"## DEAL: {deal.get('deal_name', '?')}",
        f"Stage: {deal.get('deal_stage', '?')} | MRR: {deal.get('amount', '?')}€ | Age: {deal.get('deal_age_days', '?')}d",
        f"PAE: {deal.get('pae', '?')} | PBD: {deal.get('pbd', '?')}",
    ]

    if snap:
        context_parts.append(f"\n## LATEST SNAPSHOT")
        context_parts.append(f"Probability: {snap.get('close_probability', '?')}%")
        context_parts.append(f"Assessment: {snap.get('deal_assessment') or snap.get('deal_summary', '-')}")
        context_parts.append(f"Signals: {snap.get('buyer_signals', '-')}")
        context_parts.append(f"Blockers: {snap.get('live_blockers', '-')}")
        context_parts.append(f"Next step: {snap.get('next_step', '-')}")

    context_parts.append(f"\n## MEETING INFO")
    context_parts.append(f"Type: {meeting_type}")
    context_parts.append(f"Date: {meeting.get('meeting_start', '?')}")
    context_parts.append(f"Title: {meeting.get('title', '?')}")
    context_parts.append(f"Outcome: {meeting.get('outcome', '?')}")

    if call and call.get("transcript"):
        transcript = call["transcript"][:50000]
        context_parts.append(f"\n## TRANSCRIPT ({len(transcript)} chars)")
        context_parts.append(transcript)
    else:
        deal_ctx = (deal.get("deal_context") or "")[-10000:]
        if deal_ctx:
            context_parts.append(f"\n## DEAL CONTEXT (last 10K chars, no transcript available)")
            context_parts.append(deal_ctx)

    user_prompt = "\n".join(context_parts) + "\n\n" + output_spec

    try:
        response_text = analyze(system_prompt, user_prompt, model="claudio-claude-sonnet-4-6")
        text = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())
    except Exception as e:
        print(f"    Claude evaluation failed: {e}")
        return None


def _save_evaluation(meeting: dict, evaluation: dict) -> None:
    deal = meeting.get("deal", {})
    call = meeting.get("call")

    row = {
        "call_id": call["id"] if call else None,
        "deal_id": meeting.get("deal_id"),
        "meeting_type": meeting["meeting_type"],
        "meeting_date": meeting.get("meeting_start"),
        "has_transcript": meeting.get("has_call", False),
        "owner_email": call.get("owner_email") if call else deal.get("pae"),
        "owner_name": call.get("owner_nombre") if call else deal.get("pae"),
        "deal_name": meeting.get("deal_name"),
        "deal_stage": meeting.get("deal_stage"),
        "amount": meeting.get("amount"),
        "partner": _get_team(call.get("owner_email", "")) if call else None,
        "meeting_summary": evaluation.get("meeting_summary"),
        "quality_score": evaluation.get("quality_score"),
        "signals": _to_str(evaluation.get("signals")),
        "improvements": _to_str(evaluation.get("improvements")),
        "next_step": _to_str(evaluation.get("next_step")),
        "coaching_note": evaluation.get("coaching_note"),
    }

    mt = meeting["meeting_type"]
    if mt == "first_demo":
        for k in ("m_score", "e_score", "dc_score", "dp_score", "i_score", "c_score"):
            row[k] = evaluation.get(k)
        for k in ("m_text", "e_text", "dc_text", "dp_text", "i_text", "c_text"):
            row[k] = evaluation.get(k)
    elif mt == "follow_up":
        for k in ("blockers_resolved", "blockers_remaining", "meddic_advancement", "engagement_quality"):
            row[k] = _to_str(evaluation.get(k))
    elif mt == "closing":
        for k in ("negotiation_assessment", "pricing_handling", "objection_handling", "close_timeline"):
            row[k] = _to_str(evaluation.get(k))

    row = {k: v for k, v in row.items() if v is not None}
    supabase.table("meeting_evaluations").insert(row).execute()


def _to_str(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, list):
        return "\n".join(str(v) for v in val)
    return str(val)


# ── Pipeline review ──────────────────────────────────────────────────────


def _fetch_pipeline_deals(pae_name: str) -> list[dict]:
    first_last = pae_name.split()[:2]
    pattern = f"%{'%'.join(first_last)}%" if len(first_last) >= 2 else f"%{pae_name}%"

    resp = (
        supabase.table("deals")
        .select("id, deal_name, deal_stage, amount, deal_age_days")
        .ilike("pae", pattern)
        .in_("deal_stage", list(ADVANCED_STAGES))
        .execute()
    )
    deals = resp.data or []
    if not deals:
        return []

    deal_ids = [d["id"] for d in deals]
    snap_map = {}
    for i in range(0, len(deal_ids), 30):
        batch = deal_ids[i:i + 30]
        resp2 = (
            supabase.table("front_deal_snapshots")
            .select("deal_id, close_probability, m_score, e_score, dc_score, dp_score, i_score, c_score, deal_summary, buyer_signals, live_blockers, objections, next_step, deal_strengths")
            .in_("deal_id", batch)
            .order("snapshot_date", desc=True)
            .limit(len(batch) * 2)
            .execute()
        )
        for s in (resp2.data or []):
            if s["deal_id"] not in snap_map:
                snap_map[s["deal_id"]] = s

    qualified = []
    for d in deals:
        snap = snap_map.get(d["id"])
        if snap and (snap.get("close_probability") or 0) >= MIN_PROBABILITY:
            qualified.append({"deal": d, "snap": snap})

    qualified.sort(key=lambda q: q["deal"].get("amount") or 0, reverse=True)
    return qualified


# ── Main ─────────────────────────────────────────────────────────────────


def run(pae_email: str, week_start: date | None = None, channel_override: str | None = None):
    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)
    week_end = week_start + timedelta(days=5)
    week_range = f"{week_start.isoformat()} → {(week_end - timedelta(days=1)).isoformat()}"

    pae_name = _resolve_pae_name(pae_email)
    team = _get_team(pae_email)
    channel = channel_override or TEAM_LEAD_CHANNELS.get(team, "C0ATY3V8CN4")

    print(f"{'=' * 60}")
    print(f"{pae_name} — {team} — Weekly TL Report")
    print(f"Week: {week_range}")
    print(f"Channel: {channel}")
    print(f"{'=' * 60}")

    # ── Part 1: Weekly Activity ──────────────────────────────────────
    print(f"\n▸ PART 1: WEEKLY ACTIVITY")

    pae_deal_ids = _fetch_pae_deal_ids(pae_name)
    print(f"  {len(pae_deal_ids)} deals for {pae_name}")

    meetings = _fetch_meetings_week(pae_deal_ids, pae_email, week_start, week_end)
    meetings = _enrich_meetings(meetings)
    print(f"  {len(meetings)} meetings found")

    n_demo = sum(1 for m in meetings if m["meeting_type"] == "first_demo")
    n_fu = sum(1 for m in meetings if m["meeting_type"] == "follow_up")
    n_close = sum(1 for m in meetings if m["meeting_type"] == "closing")
    n_with_audit = sum(1 for m in meetings if m.get("has_audit"))
    print(f"  Types: {n_demo} first_demo, {n_fu} follow_up, {n_close} closing")
    print(f"  With Modjo audit: {n_with_audit} / {len(meetings)}")

    if not meetings:
        print(f"  No activity — sending notice")
        send_no_demos_notice(pae_name, week_range, channel)
        return

    # Evaluate each meeting
    evaluations = []
    for i, m in enumerate(meetings, 1):
        mt = m["meeting_type"]
        dn = m.get("deal_name", "?")
        print(f"  [{i}/{len(meetings)}] {dn} ({mt}) ...", end=" ")
        ev = _evaluate_meeting(m)
        if ev:
            m["evaluation"] = ev
            _save_evaluation(m, ev)
            print(f"quality={ev.get('quality_score', '?')}")
        else:
            m["evaluation"] = None
            print("FAILED")
        evaluations.append(ev)

    # Activity synthesis
    print(f"  Generating activity synthesis ...")
    activity_system, activity_user = build_activity_synthesis(pae_name, meetings, week_start, week_end)
    activity_synthesis = _parse_json(analyze(activity_system, activity_user, model="claudio-claude-sonnet-4-6"))

    # ── Part 2: Pipeline Review ──────────────────────────────────────
    print(f"\n▸ PART 2: PIPELINE REVIEW")

    qualified = _fetch_pipeline_deals(pae_name)
    print(f"  {len(qualified)} deals (prob >= {MIN_PROBABILITY}%)")

    pipeline_synthesis = None
    if qualified:
        print(f"  Generating pipeline synthesis ...")
        pipe_system, pipe_user = build_pipeline_review(pae_name, qualified)
        pipeline_synthesis = _parse_json(analyze(pipe_system, pipe_user, model="claudio-claude-sonnet-4-6"))

    # ── Generate PDF ─────────────────────────────────────────────────
    print(f"\n▸ GENERATING PDF ...")
    try:
        pdf_bytes = generate_pdf(
            pae_name=pae_name,
            meetings=meetings,
            activity_synthesis=activity_synthesis,
            qualified_deals=qualified,
            pipeline_synthesis=pipeline_synthesis,
            week_start=week_start,
            week_end=week_end,
        )
        print(f"  PDF: {len(pdf_bytes)} bytes")
    except Exception as e:
        print(f"  PDF generation failed: {e}")
        traceback.print_exc()
        return

    # ── Send to Slack ────────────────────────────────────────────────
    print(f"\n▸ SENDING TO SLACK ({channel}) ...")
    send_demo_report(
        pdf_bytes=pdf_bytes,
        pae_name=pae_name,
        week_range=week_range,
        demo_count=len(meetings),
        mrr_total=f"{n_demo}D {n_fu}FU {n_close}CL",
        channel=channel,
    )
    print(f"  Done.")


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())
