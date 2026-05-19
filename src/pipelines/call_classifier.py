"""Classify calls by cross-referencing Modjo tags with deal stage data."""

from datetime import datetime

from src.config import TAG_AUDIT_LEVEL
from src.db.client import supabase


def classify(call: dict) -> str:
    """Determine the real call type by combining tags with deal stage.

    Returns: 'demo' | 'follow_up' | 'closing' | 'pbd_full' | 'pbd_light' | 'skip'
    """
    tags = call.get("tags") or []
    role = call.get("rol")

    if not role:
        return "skip"

    if "Partners - PAE Demo" in tags and role == "PAE":
        return "demo"

    if role == "PAE":
        deal = _find_deal(call)
        if deal and _deal_exited_demo_booked_near(deal, call.get("fecha", "")):
            return "demo"

    return _classify_from_tags(tags, role)


def _find_deal(call: dict) -> dict | None:
    hs_deal_id = call.get("hs_deal_id")
    if not hs_deal_id:
        return None
    resp = (
        supabase.table("deals")
        .select("id, deal_stage, dist_demo_booked_exited")
        .eq("deal_id", hs_deal_id)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def _deal_exited_demo_booked_near(deal: dict, call_date: str) -> bool:
    exit_date = deal.get("dist_demo_booked_exited")
    if not exit_date:
        return False

    stage = deal.get("deal_stage") or ""
    if stage in ("To reschedule", "On Hold", "Demo Booked", "New Deals"):
        return False

    try:
        exit_d = datetime.fromisoformat(exit_date[:10])
        call_d = datetime.fromisoformat(call_date[:10])
        date_match = abs((exit_d - call_d).days) <= 3
    except (ValueError, TypeError):
        date_match = False

    return date_match


def _classify_from_tags(tags: list[str], role: str) -> str:
    for tag in tags:
        level = TAG_AUDIT_LEVEL.get(tag)
        if level == "full_pae":
            return "demo"
        if level == "light_pae":
            return "closing" if "Closing" in tag else "follow_up"
        if level == "full_pbd":
            return "pbd_full"
        if level == "light":
            return "pbd_light"

    return "follow_up" if role == "PAE" else "pbd_light" if role == "PBD" else "skip"
