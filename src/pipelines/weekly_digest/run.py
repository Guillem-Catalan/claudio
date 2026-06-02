"""Weekly activity digest: all calls + deal_meetings per PAE, Claude synthesis, PDF, Slack."""

import json
import re
from datetime import date, timedelta

from src.config import TEAMS, TEAM_LEAD_CHANNELS, PAE_CHANNELS
from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.weekly_digest.prompt import build as build_prompt
from src.pipelines.weekly_digest.pdf import generate_pdf, generate_html
from src.pipelines.demo_evaluation.slack import send_demo_report, send_no_demos_notice


def run_all(
    pae_email: str | None = None,
    week_start: date | None = None,
    channel_override: str | None = None,
):
    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)
    week_end = week_start + timedelta(days=5)

    pae_emails: set[str] = set()
    for team_name, team in TEAMS.items():
        if team_name in ("Santander", "Telefónica"):
            pae_emails |= team["pae"]

    if pae_email:
        if pae_email not in pae_emails:
            print(f"  {pae_email} not in Santander/Telefónica PAE list")
            return
        pae_emails = {pae_email}

    print(f"Weekly Activity Digest: {week_start} → {week_end - timedelta(days=1)}")
    print(f"  PAEs to process: {len(pae_emails)}")

    for email in sorted(pae_emails):
        try:
            _process_pae(email, week_start, week_end, channel_override)
        except Exception as e:
            print(f"  ERROR processing {email}: {e}")


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


def _fetch_calls(pae_email: str, week_start: date, week_end: date) -> list[dict]:
    resp = (
        supabase.table("calls")
        .select("id, call_id, fecha, tags, deal_id, duracion_segundos")
        .eq("owner_email", pae_email)
        .gte("fecha", week_start.isoformat())
        .lt("fecha", week_end.isoformat())
        .order("fecha")
        .execute()
    )
    return resp.data or []


def _fetch_pae_audits(call_ref_ids: list[str]) -> dict[str, dict]:
    result = {}
    for i in range(0, len(call_ref_ids), 20):
        batch = call_ref_ids[i:i + 20]
        resp = (
            supabase.table("pae_audits")
            .select("call_ref, deal_context, buying_signals, blockers, objections, next_call_objective")
            .in_("call_ref", batch)
            .execute()
        )
        for a in (resp.data or []):
            result[a["call_ref"]] = a
    return result


def _fetch_audit_demos(call_ids: list[str]) -> dict[str, dict]:
    result = {}
    for i in range(0, len(call_ids), 20):
        batch = call_ids[i:i + 20]
        resp = (
            supabase.table("audit_demos")
            .select(
                "call_id, demo_summary, m_score, e_score, dc_score, dp_score, i_score, c_score, "
                "buyer_signals, live_blockers, next_step, objections"
            )
            .in_("call_id", batch)
            .execute()
        )
        for a in (resp.data or []):
            result[str(a["call_id"])] = a
    return result


def _fetch_deals_and_snapshots(deal_ids: list[str]) -> tuple[dict, dict]:
    deal_map: dict[str, dict] = {}
    snap_map: dict[str, dict] = {}
    for i in range(0, len(deal_ids), 30):
        batch = deal_ids[i:i + 30]
        resp = supabase.table("deals").select("id, deal_name, deal_stage, amount, deal_age_days").in_("id", batch).execute()
        for d in (resp.data or []):
            deal_map[d["id"]] = d
        resp2 = (
            supabase.table("front_deal_snapshots")
            .select("deal_id, close_probability, deal_summary")
            .in_("deal_id", batch)
            .order("snapshot_date", desc=True)
            .limit(len(batch) * 2)
            .execute()
        )
        for s in (resp2.data or []):
            if s["deal_id"] not in snap_map:
                snap_map[s["deal_id"]] = s
    return deal_map, snap_map


def _fetch_deal_meetings(pae_name: str, week_start: date, week_end: date, deal_map: dict, snap_map: dict) -> list[dict]:
    first_last = pae_name.split()[:2]
    pattern = f"%{'%'.join(first_last)}%" if len(first_last) >= 2 else f"%{pae_name}%"
    resp = supabase.table("deals").select("id").ilike("pae", pattern).execute()
    pae_deal_ids = [d["id"] for d in (resp.data or [])]

    meetings = []
    for i in range(0, len(pae_deal_ids), 30):
        batch = pae_deal_ids[i:i + 30]
        resp = (
            supabase.table("deal_meetings")
            .select("deal_id, title, meeting_start, outcome")
            .in_("deal_id", batch)
            .gte("meeting_start", week_start.isoformat())
            .lt("meeting_start", week_end.isoformat())
            .order("meeting_start")
            .execute()
        )
        meetings.extend(resp.data or [])

    for dm in meetings:
        did = dm["deal_id"]
        if did not in deal_map:
            r = supabase.table("deals").select("id, deal_name, deal_stage, amount, deal_age_days").eq("id", did).limit(1).execute()
            if r.data:
                deal_map[did] = r.data[0]
        if did not in snap_map:
            r = (
                supabase.table("front_deal_snapshots")
                .select("deal_id, close_probability, deal_summary")
                .eq("deal_id", did)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            if r.data:
                snap_map[did] = r.data[0]

    return meetings


def _build_events(calls, pae_audits, audit_demos, deal_map, snap_map, deal_meetings) -> list[dict]:
    events = []

    for c in calls:
        did = c.get("deal_id", "")
        deal = deal_map.get(did, {})
        cid = str(c.get("call_id", ""))
        pa = pae_audits.get(c["id"], {})
        ad = audit_demos.get(cid, {})
        snap = snap_map.get(did, {})
        tags = c.get("tags") or []
        is_demo = "Partners - PAE Demo" in tags
        dur = round((c.get("duracion_segundos") or 0) / 60)

        events.append({
            "type": "DEMO" if is_demo else "CALL",
            "dt": c.get("fecha", ""),
            "deal_name": deal.get("deal_name", "?"),
            "deal_stage": deal.get("deal_stage", "?"),
            "amount": deal.get("amount"),
            "prob": snap.get("close_probability"),
            "duration_min": dur,
            "audit_context": pa.get("deal_context") or ad.get("demo_summary") or "",
            "signals": pa.get("buying_signals") or ad.get("buyer_signals") or "",
            "blockers": pa.get("blockers") or ad.get("live_blockers") or "",
            "next_step": pa.get("next_call_objective") or ad.get("next_step") or "",
            "deal_snapshot": snap.get("deal_summary") or "",
            "meddic": {k: ad.get(k) for k in ["m_score", "e_score", "dc_score", "dp_score", "i_score", "c_score"]} if ad else None,
        })

    call_slots = set()
    for c in calls:
        if c.get("deal_id") and c.get("fecha"):
            call_slots.add((c["deal_id"], c["fecha"][:13]))

    for dm in deal_meetings:
        slot = (dm["deal_id"], dm["meeting_start"][:13])
        if slot in call_slots:
            continue
        deal = deal_map.get(dm["deal_id"], {})
        snap = snap_map.get(dm["deal_id"], {})
        events.append({
            "type": "MEETING",
            "dt": dm.get("meeting_start", ""),
            "deal_name": deal.get("deal_name", "?"),
            "deal_stage": deal.get("deal_stage", "?"),
            "amount": deal.get("amount"),
            "prob": snap.get("close_probability"),
            "title": dm.get("title", ""),
            "outcome": dm.get("outcome", ""),
            "deal_snapshot": snap.get("deal_summary") or "",
        })

    events.sort(key=lambda e: e["dt"])
    return events


def _generate_synthesis(pae_name: str, events: list[dict], week_start: date, week_end: date) -> dict:
    system_prompt, user_prompt = build_prompt(pae_name, events, week_start, week_end)
    response_text = analyze(system_prompt, user_prompt)
    text = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _process_pae(
    pae_email: str,
    week_start: date,
    week_end: date,
    channel_override: str | None = None,
):
    print(f"\n  --- {pae_email} ---")

    pae_name = _resolve_pae_name(pae_email)
    team = _get_team(pae_email)
    channel = channel_override or TEAM_LEAD_CHANNELS.get(team, PAE_CHANNELS.get(pae_name) or "C0ATY3V8CN4")
    week_range = f"{week_start.isoformat()} → {(week_end - timedelta(days=1)).isoformat()}"

    calls = _fetch_calls(pae_email, week_start, week_end)
    call_ref_ids = [c["id"] for c in calls]
    call_ids = [str(c["call_id"]) for c in calls if c.get("call_id")]

    pae_audits = _fetch_pae_audits(call_ref_ids) if call_ref_ids else {}
    audit_demos = _fetch_audit_demos(call_ids) if call_ids else {}

    deal_ids = list(set(c.get("deal_id") for c in calls if c.get("deal_id")))
    deal_map, snap_map = _fetch_deals_and_snapshots(deal_ids) if deal_ids else ({}, {})

    deal_meetings = _fetch_deal_meetings(pae_name, week_start, week_end, deal_map, snap_map)

    events = _build_events(calls, pae_audits, audit_demos, deal_map, snap_map, deal_meetings)

    if not events:
        print(f"  No activity — sending notice")
        send_no_demos_notice(pae_name, week_range, channel)
        return

    n_demo = sum(1 for e in events if e["type"] == "DEMO")
    n_call = sum(1 for e in events if e["type"] == "CALL")
    n_meet = sum(1 for e in events if e["type"] == "MEETING")
    print(f"  {len(events)} events ({n_demo} demos, {n_call} calls, {n_meet} meetings)")

    print(f"  Generating Claude synthesis ...")
    synthesis = _generate_synthesis(pae_name, events, week_start, week_end)

    print(f"  Generating PDF ...")
    try:
        pdf_bytes = generate_pdf(pae_name, events, synthesis, week_start, week_end)
        print(f"  PDF: {len(pdf_bytes)} bytes")
    except Exception as e:
        if "gobject" in str(e).lower() or "pango" in str(e).lower():
            print(f"  WeasyPrint not available — writing HTML preview")
            html = generate_html(pae_name, events, synthesis, week_start, week_end)
            path = f"/tmp/weekly-digest-{pae_name.lower().replace(' ', '-')}.html"
            with open(path, "w") as f:
                f.write(html)
            print(f"  HTML: {path}")
            return
        raise

    print(f"  Sending to Slack ({channel}) ...")
    send_demo_report(
        pdf_bytes=pdf_bytes,
        pae_name=pae_name,
        week_range=week_range,
        demo_count=len(events),
        mrr_total=f"{len(events)} interacciones",
        channel=channel,
    )
    print(f"  Done.")
