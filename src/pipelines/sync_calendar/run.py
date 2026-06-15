"""
Sync Google Calendar → calendar_meetings (passive mirror).

Two modes:
  - sync_today(): Fetch PAE calendars for today, resolve attendees → deals, upsert.
  - reconcile_yesterday(): Check which planned meetings were registered in the deal. Alert Slack.
"""

import os
from datetime import datetime, timezone, timedelta

from src.config import TEAMS
from src.db.client import supabase
from src.pipelines.sync_calendar.gcal_client import fetch_events
from src.pipelines.sync_calendar.resolver import (
    is_external,
    is_prospect,
    prospect_domains,
    resolve_event,
    clear_cache,
)

SLACK_CHANNEL = os.environ.get("SLACK_CALENDAR_CHANNEL", "")

_INTERNAL_KEYWORDS = [
    "weekly", "daily", "1:1", "1 to 1", "sync", "sincro",
    "standup", "stand-up", "retro", "planning", "sprint",
    "partner sales team",
]


def _is_internal_title(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in _INTERNAL_KEYWORDS)


def _pae_calendars() -> list[dict]:
    """Build list of PAE calendars from all active teams."""
    calendars = []
    for team_name, team in TEAMS.items():
        if not team.get("active"):
            continue
        for email in sorted(team.get("pae", set())):
            name = email.split("@")[0].replace(".", " ").title()
            calendars.append({"email": email, "name": name, "team": team_name})
    return calendars


def _resolve_deal_uuid(hs_deal_id: str) -> tuple[str | None, str | None]:
    """Lookup Supabase deal UUID and name from HS deal ID."""
    result = (
        supabase.table("deals")
        .select("id, deal_name")
        .eq("deal_id", hs_deal_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"], result.data[0].get("deal_name", "")
    return None, None


def sync_today(target_date: datetime | None = None):
    """Fetch today's calendar events for all PAEs and upsert to calendar_meetings."""
    now = target_date or datetime.now(timezone.utc)
    cest_offset = timedelta(hours=2)
    local_now = now + cest_offset
    day_str = local_now.strftime("%Y-%m-%d")

    time_min = f"{day_str}T00:00:00+02:00"
    time_max = f"{day_str}T23:59:59+02:00"

    print(f"=== Sync Calendar for {day_str} ===\n")

    calendars = _pae_calendars()
    print(f"PAE calendars: {len(calendars)}")

    total_events = 0
    total_resolved = 0
    total_unresolved = 0
    total_partner_only = 0
    rows: list[dict] = []

    for cal in calendars:
        email = cal["email"]
        name = cal["name"]

        events = fetch_events(email, time_min, time_max)
        if not events:
            continue

        external_events = []
        for ev in events:
            if _is_internal_title(ev.get("title", "")):
                continue
            attendees = ev.get("attendees", [])
            has_external = any(is_external(a["email"]) for a in attendees)
            if has_external:
                external_events.append(ev)

        if not external_events:
            continue

        print(f"\n  {name} ({email}): {len(external_events)} external meetings")

        for ev in external_events:
            attendees = ev["attendees"]
            external_attendees = [a for a in attendees if is_external(a["email"])]

            # Check if any attendee is a prospect (not partner, not internal)
            domains = prospect_domains(attendees)
            if not domains:
                total_partner_only += 1
                print(f"    ⊘ {ev['title'][:50]} → solo partner (skip)")
                continue

            total_events += 1
            deal_matches = resolve_event(attendees)

            if deal_matches:
                # Write one row per resolved deal
                for match in deal_matches:
                    row = {
                        "gcal_event_id": f"{email}:{ev['gcal_event_id']}:{match['deal_id']}",
                        "gcal_calendar_id": email,
                        "pae_email": email,
                        "pae_name": name,
                        "meeting_start": ev["meeting_start"],
                        "meeting_end": ev.get("meeting_end"),
                        "title": ev.get("title", ""),
                        "attendees": external_attendees,
                        "resolved": True,
                        "matched": False,
                        "hs_deal_id": match["hs_deal_id"],
                        "deal_id": match["deal_id"],
                        "deal_name": match["deal_name"],
                    }
                    rows.append(row)
                    total_resolved += 1
                    print(f"    ✓ {ev['title'][:50]} → {match['deal_name'][:40]}")
            else:
                total_unresolved += 1
                row = {
                    "gcal_event_id": f"{email}:{ev['gcal_event_id']}",
                    "gcal_calendar_id": email,
                    "pae_email": email,
                    "pae_name": name,
                    "meeting_start": ev["meeting_start"],
                    "meeting_end": ev.get("meeting_end"),
                    "title": ev.get("title", ""),
                    "attendees": external_attendees,
                    "resolved": False,
                    "matched": False,
                }
                rows.append(row)
                print(f"    ? {ev['title'][:50]} → sin deal")

    if rows:
        for r in rows:
            if r.get("deal_id") is None:
                r.pop("deal_id", None)

        written = 0
        for i in range(0, len(rows), 100):
            batch = rows[i : i + 100]
            result = (
                supabase.table("calendar_meetings")
                .upsert(batch, on_conflict="gcal_event_id")
                .execute()
            )
            written += len(result.data or [])
        print(f"\n  Upserted: {written} calendar meetings")

    # Remove cancelled events: events in DB for today that are no longer in Google Calendar
    synced_event_ids = {r["gcal_event_id"] for r in rows}
    existing_result = (
        supabase.table("calendar_meetings")
        .select("id, gcal_event_id")
        .gte("meeting_start", time_min)
        .lte("meeting_start", time_max)
        .execute()
    )
    existing_events = existing_result.data or []
    to_delete = [e["id"] for e in existing_events if e["gcal_event_id"] not in synced_event_ids]
    if to_delete:
        for i in range(0, len(to_delete), 100):
            supabase.table("calendar_meetings").delete().in_("id", to_delete[i:i+100]).execute()
        print(f"  Deleted {len(to_delete)} cancelled events")

    # Cleanup old meetings (>7 days)
    cutoff = (now - timedelta(days=7)).isoformat()
    supabase.table("calendar_meetings").delete().lt("meeting_start", cutoff).execute()

    print(f"\nDone: {total_events} prospect meetings, "
          f"{total_resolved} resolved to deal, {total_unresolved} unresolved, "
          f"{total_partner_only} partner-only (skipped)")

    clear_cache()


def reconcile_yesterday(target_date: datetime | None = None):
    """Check which of yesterday's planned meetings were actually registered."""
    now = target_date or datetime.now(timezone.utc)
    cest_offset = timedelta(hours=2)
    local_yesterday = (now + cest_offset) - timedelta(days=1)
    day_str = local_yesterday.strftime("%Y-%m-%d")

    print(f"\n=== Reconcile Calendar for {day_str} ===\n")

    cal_result = (
        supabase.table("calendar_meetings")
        .select("*")
        .gte("meeting_start", f"{day_str}T00:00:00Z")
        .lte("meeting_start", f"{day_str}T23:59:59Z")
        .eq("resolved", True)
        .execute()
    )
    cal_meetings = cal_result.data or []

    if not cal_meetings:
        print("  No resolved calendar meetings yesterday.")
        return

    print(f"  {len(cal_meetings)} resolved meetings to check")

    hs_result = (
        supabase.table("deal_meetings")
        .select("deal_id, meeting_start")
        .gte("meeting_start", f"{day_str}T00:00:00Z")
        .lte("meeting_start", f"{day_str}T23:59:59Z")
        .execute()
    )
    hs_deals_yesterday = {r["deal_id"] for r in (hs_result.data or []) if r.get("deal_id")}

    calls_result = (
        supabase.table("calls")
        .select("deal_id, fecha")
        .gte("fecha", f"{day_str}T00:00:00Z")
        .lte("fecha", f"{day_str}T23:59:59Z")
        .execute()
    )
    call_deals_yesterday = {r["deal_id"] for r in (calls_result.data or []) if r.get("deal_id")}

    all_active_deals = hs_deals_yesterday | call_deals_yesterday

    matched_ids = []
    unmatched = []

    for cm in cal_meetings:
        deal_id = cm.get("deal_id")
        if deal_id and deal_id in all_active_deals:
            matched_ids.append(cm["id"])
        else:
            unmatched.append(cm)

    if matched_ids:
        for i in range(0, len(matched_ids), 100):
            batch = matched_ids[i : i + 100]
            supabase.table("calendar_meetings").update({"matched": True}).in_("id", batch).execute()

    print(f"  Matched: {len(matched_ids)}")
    print(f"  Unmatched: {len(unmatched)}")

    if unmatched and SLACK_CHANNEL:
        _send_slack_alert(day_str, len(matched_ids), unmatched)


def _send_slack_alert(day_str: str, matched_count: int, unmatched: list[dict]):
    """Post reconciliation report to Slack."""
    from src.pipelines.eb_alert.slack import SlackClient

    slack = SlackClient()

    lines = [f"*📅 Reconciliación Calendar — {day_str}*\n"]
    lines.append(f"✅ {matched_count} meetings previstos → registrados en deal")
    lines.append(f"⚠️ {len(unmatched)} meetings previstos → *NO registrados:*\n")

    for cm in unmatched:
        time_str = cm.get("meeting_start", "?")[11:16]
        title = cm.get("title", "(sin título)")[:50]
        pae = cm.get("pae_name", "?")
        deal_name = cm.get("deal_name", "")

        if deal_name:
            lines.append(f"• {time_str} — {title}\n  PAE: {pae} | Deal: {deal_name}")
        else:
            lines.append(f"• {time_str} — {title}\n  PAE: {pae} | ⚠️ Sin deal asociado")

    text = "\n".join(lines)
    slack.post_message(SLACK_CHANNEL, {"text": text})
    print(f"  Slack alert sent to {SLACK_CHANNEL}")


def run(mode: str = "full", target_date: datetime | None = None):
    """Entry point. mode='full' does reconcile+sync, mode='refresh' does sync only."""
    if mode == "full":
        reconcile_yesterday(target_date=target_date)
    sync_today(target_date=target_date)
