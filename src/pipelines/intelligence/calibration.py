"""
Monthly calibration: compare forecast predictions vs actual outcomes.
Generates calibration_log entries for the model to learn from errors.
"""

import json
import re
from datetime import date, timedelta
from src.db.client import supabase
from src.integrations.claude import analyze


def calibrate_month(target_month: str | None = None):
    """Compare forecast predictions for a month vs actual results."""
    if not target_month:
        last_month = date.today().replace(day=1) - timedelta(days=1)
        target_month = last_month.strftime("%Y-%m")

    year, month = target_month.split("-")
    month_start = f"{target_month}-01"
    next_month = date(int(year), int(month), 1) + timedelta(days=32)
    month_end = next_month.replace(day=1).isoformat()

    print(f"Calibrating forecast for {target_month} ...")

    # Get all deals that had closes_this_month=true for this month
    predicted_resp = (
        supabase.table("front_deal_snapshots")
        .select("deal_id, closes_this_month, forecast_confidence, forecast_reasoning")
        .eq("closes_this_month", True)
        .gte("snapshot_date", month_start)
        .lt("snapshot_date", month_end)
        .execute()
    )

    predicted_deal_ids = list(set(
        s["deal_id"] for s in (predicted_resp.data or []) if s.get("deal_id")
    ))

    if not predicted_deal_ids:
        print(f"  No forecast predictions found for {target_month}.")
        return

    # Get actual outcomes
    deal_resp = (
        supabase.table("deals")
        .select("id, deal_name, deal_stage, close_date")
        .in_("id", predicted_deal_ids)
        .execute()
    )
    deal_map = {d["id"]: d for d in (deal_resp.data or [])}

    entries = []
    for deal_id in predicted_deal_ids:
        d = deal_map.get(deal_id)
        if not d:
            continue

        stage = (d.get("deal_stage") or "").lower()
        close_date = d.get("close_date") or ""

        if "closed won" in stage and close_date >= month_start and close_date < month_end:
            actual = "closed_won_this_month"
        elif "closed won" in stage:
            actual = "closed_won_other_month"
        elif "closed lost" in stage or "opportunity lost" in stage:
            actual = "lost"
        else:
            actual = "still_open"

        is_error = actual != "closed_won_this_month"

        entries.append({
            "month": target_month,
            "deal_id": deal_id,
            "deal_name": d.get("deal_name"),
            "predicted_close_this_month": True,
            "actual_outcome": actual,
            "error_analysis": _analyze_error(d, actual) if is_error else "Correct prediction.",
        })

    # Also find deals that closed this month but were NOT predicted
    closed_resp = (
        supabase.table("deals")
        .select("id, deal_name")
        .in_("deal_stage", ["Closed Won", "Closed won", "Closed Won - Finance Only"])
        .gte("close_date", month_start)
        .lt("close_date", month_end)
        .execute()
    )
    closed_ids = {d["id"] for d in (closed_resp.data or [])}
    missed = closed_ids - set(predicted_deal_ids)

    for deal_id in list(missed)[:20]:
        d_resp = supabase.table("deals").select("id, deal_name").eq("id", deal_id).limit(1).execute()
        if d_resp.data:
            entries.append({
                "month": target_month,
                "deal_id": deal_id,
                "deal_name": d_resp.data[0].get("deal_name"),
                "predicted_close_this_month": False,
                "actual_outcome": "closed_won_this_month",
                "error_analysis": "False negative — deal closed but Claudio didn't predict it.",
            })

    for e in entries:
        supabase.table("calibration_log").insert(e).execute()

    correct = sum(1 for e in entries if e["actual_outcome"] == "closed_won_this_month" and e["predicted_close_this_month"])
    false_pos = sum(1 for e in entries if e["actual_outcome"] != "closed_won_this_month" and e["predicted_close_this_month"])
    false_neg = sum(1 for e in entries if e["actual_outcome"] == "closed_won_this_month" and not e["predicted_close_this_month"])

    print(f"  Results: {correct} correct, {false_pos} false positives, {false_neg} false negatives")
    print(f"  Total entries: {len(entries)}")


def _analyze_error(deal: dict, actual: str) -> str:
    stage = deal.get("deal_stage", "?")
    name = deal.get("deal_name", "?")
    if actual == "lost":
        return f"Deal went to {stage} instead of closing. Claudio was too optimistic."
    elif actual == "still_open":
        return f"Deal still in {stage} — hasn't closed yet. Timing was wrong."
    elif actual == "closed_won_other_month":
        return f"Deal did close but not this month. Timing estimate was off."
    return "Unknown error."
