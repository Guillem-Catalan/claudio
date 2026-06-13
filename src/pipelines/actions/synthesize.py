"""
Synthesize unified deal actions from snapshot data.
Converts relative timing ('hoy', 'esta semana') to absolute dates.
Excludes closed/lost deals.
No Claude call — pure parsing.
"""

import json
import re
from datetime import date, timedelta

from src.db.client import supabase
from src.config import ALL_PBD_EMAILS, ALL_PAE_EMAILS

EXCLUDE_STAGES = {
    "Opportunity lost", "Closed lost", "Closed Lost", "Closed Won", "Closed won",
    "Closed Won - Finance Only", "Opportunity Lost",
    "Onboarding Completed - Converted", "Onboarding Completed - Pending Conversion",
    "Onboarding Failed", "Onboarding On Hold",
    "Churned (Closed)", "Retained (Closed)", "Preventive Churn Risk (New)",
    "Requested Churn (New)", "(DO NOT USE) Churn Confirmed",
    "Wrongly Created Ticket (Closed)", "SPAM",
}

EXCLUDE_PIPELINES = {"Onboarding Pipeline", "Upselling Pipeline", "Churn Pipeline"}


def _parse_action_type(text: str) -> str:
    t = text.upper()
    if "[CALL]" in t or "llamar" in text.lower() or "call" in text.lower() or "chiamare" in text.lower():
        return "CALL"
    if "[EMAIL]" in t or "email" in text.lower() or "enviar" in text.lower() or "escribir" in text.lower() or "scrivere" in text.lower():
        return "EMAIL"
    if "[ROI]" in t or "roi" in text.lower() or "business case" in text.lower():
        return "ROI"
    if "[SLIDES]" in t or "slides" in text.lower() or "presentación" in text.lower() or "deck" in text.lower():
        return "SLIDES"
    if "[BATTLECARD]" in t or "battlecard" in text.lower() or "comparativa" in text.lower():
        return "BATTLECARD"
    return "PREP"


def _parse_who_and_text(raw: str) -> tuple[str, str]:
    clean = re.sub(r"\[(?:CALL|EMAIL|ROI|SLIDES|BATTLECARD)\]\s*", "", raw).strip()
    clean = re.sub(r"^[•\-\d.]\s*", "", clean).strip()
    arrow = clean.find("→")
    if 0 < arrow < 30:
        who = clean[:arrow].strip()
        text = clean[arrow + 1:].strip()
        if text:
            text = text[0].upper() + text[1:]
        return who, text
    return "", clean[0].upper() + clean[1:] if clean else ""


def _resolve_due_date(text: str, snapshot_date: date) -> date:
    """Convert relative timing to absolute date using snapshot_date as reference."""
    t = text.lower()

    # 1. Explicit dates: DD/MM, DD/MM/YYYY, DD de mes
    explicit = re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", t)
    if explicit:
        day, month = int(explicit.group(1)), int(explicit.group(2))
        year = int(explicit.group(3)) if explicit.group(3) else snapshot_date.year
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            pass

    months_es = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                 "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    month_match = re.search(r"(\d{1,2}) de (\w+)", t)
    if month_match:
        day = int(month_match.group(1))
        month_name = month_match.group(2).lower()
        if month_name in months_es:
            try:
                return date(snapshot_date.year, months_es[month_name], day)
            except ValueError:
                pass

    # 2. Relative dates
    if "hoy" in t or "ahora" in t or "inmediatamente" in t or "today" in t:
        return snapshot_date

    if "mañana" in t or "tomorrow" in t:
        return snapshot_date + timedelta(days=1)

    # Day names → next occurrence from snapshot_date
    day_names = {"lunes": 0, "martes": 1, "miércoles": 2, "jueves": 3, "viernes": 4}
    for name, weekday in day_names.items():
        if name in t:
            days_ahead = weekday - snapshot_date.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return snapshot_date + timedelta(days=days_ahead)

    if "esta semana" in t or "this week" in t:
        # Friday of the snapshot week
        days_to_friday = 4 - snapshot_date.weekday()
        if days_to_friday < 0:
            days_to_friday += 7
        return snapshot_date + timedelta(days=days_to_friday)

    if "próxima semana" in t or "semana que viene" in t or "next week" in t:
        # Monday of next week
        days_to_monday = 7 - snapshot_date.weekday()
        return snapshot_date + timedelta(days=days_to_monday)

    if "este mes" in t or "this month" in t:
        # Last day of month
        if snapshot_date.month == 12:
            return date(snapshot_date.year + 1, 1, 1) - timedelta(days=1)
        return date(snapshot_date.year, snapshot_date.month + 1, 1) - timedelta(days=1)

    # Default: snapshot_date + 3 days (reasonable follow-up window)
    return snapshot_date + timedelta(days=3)


def _format_when_label(due: date, today: date) -> str:
    """Human-readable label relative to today."""
    diff = (due - today).days
    if diff < 0:
        return f"atrasado ({abs(diff)}d)"
    if diff == 0:
        return "hoy"
    if diff == 1:
        return "mañana"
    if diff < 7:
        day_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        return day_names[due.weekday()]
    if diff < 14:
        return "próxima semana"
    return due.isoformat()


def _parse_next_step_lines(next_step: str | None, snapshot_dt: date) -> list[dict]:
    if not next_step:
        return []
    result = []
    for line in next_step.split("\n"):
        line = line.strip()
        if not line or len(line) < 5:
            continue
        line = re.sub(r"^[•\-]\s*", "", line).strip()
        if not line:
            continue
        action_type = _parse_action_type(line)
        who, text = _parse_who_and_text(line)
        due = _resolve_due_date(line, snapshot_dt)
        result.append({"type": action_type, "who": who, "text": text, "due": due.isoformat()})
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


def _determine_priority(bucket: str, due: date, today: date) -> int:
    diff = (due - today).days
    if diff <= 0 and bucket in ("forecast", "pushable"):
        return 1
    if bucket == "forecast":
        return 1
    if diff <= 0:
        return 2
    if bucket == "pushable":
        return 2
    if bucket == "next_month":
        return 3
    if bucket == "blocker":
        return 4
    return 5


def synthesize_for_deal(deal_uuid: str) -> dict | None:
    deal_resp = supabase.table("deals").select(
        "id, deal_name, deal_stage, amount, pae, pbd, close_date, pipeline_name"
    ).eq("id", deal_uuid).maybe_single().execute()
    if not deal_resp.data:
        return None
    d = deal_resp.data

    # Exclude closed/lost/churn deals
    stage = d.get("deal_stage") or ""
    if stage in EXCLUDE_STAGES:
        return None
    pipeline = d.get("pipeline_name") or ""
    if pipeline in EXCLUDE_PIPELINES:
        return None

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

    snap_date_str = snap.get("snapshot_date") or date.today().isoformat()
    try:
        snapshot_dt = date.fromisoformat(str(snap_date_str))
    except ValueError:
        snapshot_dt = date.today()

    today = date.today()

    # Parse next_step lines with absolute dates
    ns_lines = _parse_next_step_lines(snap.get("next_step"), snapshot_dt)

    # Determine headline
    push_action = (snap.get("push_action") or "").strip()
    action_signal = (snap.get("action_signal") or "").strip()

    if push_action:
        who, headline = _parse_who_and_text(push_action)
        action_type = _parse_action_type(push_action)
        due = _resolve_due_date(push_action, snapshot_dt)
    elif action_signal:
        who = d.get("pae") or d.get("pbd") or ""
        headline = action_signal[0].upper() + action_signal[1:] if action_signal else ""
        action_type = _parse_action_type(action_signal)
        due = _resolve_due_date(action_signal, snapshot_dt)
    elif ns_lines:
        first = ns_lines[0]
        who = first["who"]
        headline = first["text"]
        action_type = first["type"]
        due = date.fromisoformat(first["due"])
    else:
        return None

    if not who:
        who = d.get("pae") or d.get("pbd") or "Rep"

    detail = push_action if push_action else (snap.get("forecast_accelerators") or "")

    follow_ups = []
    for i, ns in enumerate(ns_lines[1:5], start=2):
        follow_ups.append({
            "order": i, "type": ns["type"], "who": ns["who"] or who,
            "text": ns["text"], "when": _format_when_label(date.fromisoformat(ns["due"]), today),
        })

    bucket = _determine_bucket(snap)
    priority = _determine_priority(bucket, due, today)
    when_label = _format_when_label(due, today)
    owner = d.get("pae") or d.get("pbd") or ""

    # Determine if the action is for a PAE or PBD
    # Try to match action_who to known emails
    who_lower = who.lower().replace(" ", ".")
    who_email_guess = who_lower + "@factorial.co" if who_lower else ""
    pbd_name = (d.get("pbd") or "").lower()
    pae_name = (d.get("pae") or "").lower()

    if who_email_guess in ALL_PBD_EMAILS and who_email_guess not in ALL_PAE_EMAILS:
        action_role = "pbd"
    elif pbd_name and who.lower().startswith(pbd_name.split()[0]) and who.lower() != pae_name.lower():
        action_role = "pbd"
    else:
        action_role = "pae"

    row = {
        "deal_id": deal_uuid,
        "snapshot_date": snap_date_str,
        "action_headline": headline[:200],
        "action_detail": detail[:500] if detail else None,
        "action_type": action_type,
        "action_who": who,
        "action_when": when_label,
        "action_due_date": due.isoformat(),
        "action_priority": priority,
        "action_role": action_role,
        "follow_ups": json.dumps(follow_ups),
        "deal_name": d.get("deal_name"),
        "deal_owner": owner,
        "deal_mrr": d.get("amount"),
        "deal_stage": stage,
        "bucket": bucket,
        "claudio_close_date": snap.get("claudio_close_date"),
        "status": "pending",
        "updated_at": "now()",
    }
    row = {k: v for k, v in row.items() if v is not None}

    supabase.table("deal_actions").upsert(
        row, on_conflict="deal_id,snapshot_date"
    ).execute()
    return row


def synthesize_all():
    """Synthesize actions for ALL active deals with snapshots."""
    print("Synthesizing deal actions ...")

    all_deal_ids: set[str] = set()
    offset = 0
    PAGE = 1000
    while True:
        resp = (
            supabase.table("front_deal_snapshots")
            .select("deal_id")
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        rows = resp.data or []
        for r in rows:
            all_deal_ids.add(r["deal_id"])
        if len(rows) < PAGE:
            break
        offset += PAGE

    print(f"  Found {len(all_deal_ids)} unique deals with snapshots")

    ok = 0
    skipped = 0
    errors = 0
    for i, deal_id in enumerate(all_deal_ids):
        try:
            result = synthesize_for_deal(deal_id)
            if result:
                ok += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error for {deal_id}: {e}")
        if (i + 1) % 100 == 0:
            print(f"  ... {i + 1}/{len(all_deal_ids)} processed ({ok} ok, {skipped} skipped)")

    print(f"  Synthesized {ok} actions, {skipped} skipped, {errors} errors from {len(all_deal_ids)} deals.")
    return ok
