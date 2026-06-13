"""
Synthesize unified deal actions from snapshot data.
Runs after snapshot generation in run_deals.
No Claude call — pure parsing and merging of existing snapshot fields.
"""

import json
import re
from datetime import date

from src.db.client import supabase


def _parse_action_type(text: str) -> str:
    t = text.upper()
    if "[CALL]" in t or "llamar" in text.lower() or "call" in text.lower():
        return "CALL"
    if "[EMAIL]" in t or "email" in text.lower() or "enviar" in text.lower() or "escribir" in text.lower():
        return "EMAIL"
    if "[ROI]" in t or "roi" in text.lower() or "business case" in text.lower():
        return "ROI"
    if "[SLIDES]" in t or "slides" in text.lower() or "presentación" in text.lower() or "deck" in text.lower():
        return "SLIDES"
    if "[BATTLECARD]" in t or "battlecard" in text.lower() or "comparativa" in text.lower():
        return "BATTLECARD"
    return "PREP"


def _parse_who_and_text(raw: str) -> tuple[str, str]:
    """Extract 'who → action' from text like 'Xavier → llamar a Carlos...'"""
    clean = re.sub(r"\[(?:CALL|EMAIL|ROI|SLIDES|BATTLECARD)\]\s*", "", raw).strip()
    clean = re.sub(r"^[•\-\d.]\s*", "", clean).strip()

    arrow = clean.find("→")
    if arrow > 0 and arrow < 30:
        who = clean[:arrow].strip()
        text = clean[arrow + 1:].strip()
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        return who, text

    return "", clean[0].upper() + clean[1:] if clean else ""


def _parse_when(text: str) -> str:
    t = text.lower()
    if "hoy" in t or "ahora" in t or "today" in t or "inmediatamente" in t:
        return "hoy"
    if "mañana" in t or "tomorrow" in t:
        return "mañana"

    # Match "antes del DD/MM" or "antes del DD de mes"
    m = re.search(r"antes del (\d{1,2}[/\-]\d{1,2}|\d{1,2} de \w+)", t)
    if m:
        return "antes del " + m.group(1)

    if "esta semana" in t or "this week" in t:
        return "esta semana"
    if "semana que viene" in t or "próxima semana" in t or "next week" in t:
        return "próxima semana"
    if "este mes" in t or "this month" in t:
        return "este mes"

    # Match "viernes", "lunes", etc.
    for day in ["lunes", "martes", "miércoles", "jueves", "viernes"]:
        if day in t:
            return day

    return "pendiente"


def _parse_next_step_lines(next_step: str | None) -> list[dict]:
    if not next_step:
        return []
    lines = next_step.split("\n")
    result = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        line = re.sub(r"^[•\-]\s*", "", line).strip()
        if not line:
            continue
        action_type = _parse_action_type(line)
        who, text = _parse_who_and_text(line)
        when = _parse_when(line)
        result.append({
            "type": action_type,
            "who": who,
            "text": text,
            "when": when,
        })
    return result


def _determine_bucket(snap: dict) -> str:
    if snap.get("closes_this_month"):
        return "forecast"
    if snap.get("forecast_pushable"):
        return "pushable"
    if snap.get("closes_next_month"):
        return "next_month"
    blockers = snap.get("live_blockers") or ""
    if blockers.strip() and len(blockers.strip()) > 5:
        return "blocker"
    return "pipeline"


def _determine_priority(bucket: str, when: str) -> int:
    if when == "hoy":
        return 1
    if bucket == "forecast":
        return 1
    if bucket == "pushable":
        return 2
    if bucket == "next_month":
        return 3
    if bucket == "blocker":
        return 4
    return 5


def synthesize_for_deal(deal_uuid: str) -> dict | None:
    """Create or update the deal_action for a deal based on its latest snapshot."""

    # Get deal info
    deal_resp = supabase.table("deals").select(
        "id, deal_name, deal_stage, amount, pae, pbd, close_date"
    ).eq("id", deal_uuid).maybe_single().execute()
    if not deal_resp.data:
        return None
    d = deal_resp.data

    # Get latest snapshot
    snap_resp = (
        supabase.table("front_deal_snapshots")
        .select(
            "action_signal, push_action, next_step, forecast_accelerators, "
            "closes_this_month, closes_next_month, forecast_pushable, "
            "live_blockers, claudio_close_date, snapshot_date"
        )
        .eq("deal_id", deal_uuid)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    if not snap_resp.data:
        return None
    snap = snap_resp.data[0]

    # Parse all next_step lines
    ns_lines = _parse_next_step_lines(snap.get("next_step"))

    # Determine headline: push_action > action_signal > first next_step
    push_action = (snap.get("push_action") or "").strip()
    action_signal = (snap.get("action_signal") or "").strip()

    if push_action:
        who, headline = _parse_who_and_text(push_action)
        action_type = _parse_action_type(push_action)
        when = _parse_when(push_action)
    elif action_signal:
        who = d.get("pae") or d.get("pbd") or ""
        headline = action_signal[0].upper() + action_signal[1:] if action_signal else ""
        action_type = _parse_action_type(action_signal)
        when = _parse_when(action_signal)
    elif ns_lines:
        first = ns_lines[0]
        who = first["who"]
        headline = first["text"]
        action_type = first["type"]
        when = first["when"]
    else:
        return None

    if not who:
        who = d.get("pae") or d.get("pbd") or "Rep"

    # Build detail from accelerators or push_action full text
    detail = push_action if push_action else (snap.get("forecast_accelerators") or "")

    # Build follow_ups from next_step lines 2+
    follow_ups = []
    for i, ns in enumerate(ns_lines[1:5], start=2):
        follow_ups.append({
            "order": i,
            "type": ns["type"],
            "who": ns["who"] or who,
            "text": ns["text"],
            "when": ns["when"],
        })

    bucket = _determine_bucket(snap)
    priority = _determine_priority(bucket, when)

    owner = d.get("pae") or d.get("pbd") or ""
    today_str = date.today().isoformat()

    row = {
        "deal_id": deal_uuid,
        "snapshot_date": snap.get("snapshot_date") or today_str,
        "action_headline": headline[:200],
        "action_detail": detail[:500] if detail else None,
        "action_type": action_type,
        "action_who": who,
        "action_when": when,
        "action_priority": priority,
        "follow_ups": json.dumps(follow_ups),
        "deal_name": d.get("deal_name"),
        "deal_owner": owner,
        "deal_mrr": d.get("amount"),
        "deal_stage": d.get("deal_stage"),
        "bucket": bucket,
        "claudio_close_date": snap.get("claudio_close_date"),
        "status": "pending",
        "updated_at": "now()",
    }
    row = {k: v for k, v in row.items() if v is not None}

    # Upsert (unique on deal_id + snapshot_date)
    supabase.table("deal_actions").upsert(
        row, on_conflict="deal_id,snapshot_date"
    ).execute()

    return row


def synthesize_all():
    """Synthesize actions for all deals that have a recent snapshot."""
    print("Synthesizing deal actions ...")

    # Get all deals with a snapshot from today or yesterday
    today = date.today().isoformat()
    snap_resp = (
        supabase.table("front_deal_snapshots")
        .select("deal_id")
        .gte("snapshot_date", today)
        .execute()
    )
    deal_ids = list({s["deal_id"] for s in (snap_resp.data or [])})

    if not deal_ids:
        # Fallback: get latest snapshot per deal
        snap_resp = (
            supabase.table("front_deal_snapshots")
            .select("deal_id")
            .order("snapshot_date", desc=True)
            .limit(500)
            .execute()
        )
        deal_ids = list({s["deal_id"] for s in (snap_resp.data or [])})

    ok = 0
    for deal_id in deal_ids:
        try:
            result = synthesize_for_deal(deal_id)
            if result:
                ok += 1
        except Exception as e:
            print(f"  Error for {deal_id}: {e}")

    print(f"  Synthesized {ok} actions from {len(deal_ids)} deals.")
    return ok
