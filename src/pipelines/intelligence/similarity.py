"""
Find similar historical deals for benchmark comparison.
Used by forecast_v2 and other agents.
"""

import json
from src.db.client import supabase


def find_similar(
    deal_stage: str,
    amount: float | None,
    deal_age_days: int | None,
    team: str | None = None,
    outcome_filter: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Find similar deals from deal_trajectories.

    Matching priority:
    1. Same outcome bucket (won/lost) if filtered
    2. Similar amount range (±50% or same bucket)
    3. Similar deal age (±30%)
    4. Same team if provided
    """
    query = supabase.table("deal_trajectories").select(
        "deal_id, outcome, amount, deal_age_days, pae, team, "
        "closed_lost_reason, close_date, trajectory, lessons"
    )

    if outcome_filter:
        query = query.eq("outcome", outcome_filter)

    if team:
        query = query.eq("team", team)

    resp = query.order("created_at", desc=True).limit(200).execute()
    candidates = resp.data or []

    if not candidates:
        return []

    def _score(c: dict) -> float:
        s = 0.0
        c_amount = float(c.get("amount") or 0)
        c_age = c.get("deal_age_days") or 0

        if amount and c_amount:
            ratio = min(amount, c_amount) / max(amount, c_amount) if max(amount, c_amount) > 0 else 0
            s += ratio * 3

        if deal_age_days and c_age:
            ratio = min(deal_age_days, c_age) / max(deal_age_days, c_age) if max(deal_age_days, c_age) > 0 else 0
            s += ratio * 2

        return s

    scored = [(c, _score(c)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for c, score in scored[:limit]:
        traj = c.get("trajectory")
        if isinstance(traj, str):
            try:
                traj = json.loads(traj)
            except (json.JSONDecodeError, TypeError):
                traj = []
        lessons = c.get("lessons")
        if isinstance(lessons, str):
            try:
                lessons = json.loads(lessons)
            except (json.JSONDecodeError, TypeError):
                lessons = []

        results.append({
            "outcome": c["outcome"],
            "amount": c.get("amount"),
            "deal_age_days": c.get("deal_age_days"),
            "pae": c.get("pae"),
            "team": c.get("team"),
            "closed_lost_reason": c.get("closed_lost_reason"),
            "close_date": c.get("close_date"),
            "trajectory_summary": _summarize_trajectory(traj),
            "lessons": lessons or [],
        })

    return results


def _summarize_trajectory(traj: list[dict]) -> str:
    """Summarize a trajectory into a compact text for prompt injection."""
    if not traj:
        return "No trajectory data."

    lines = []
    for t in traj[-8:]:
        prob = t.get("probability", "?")
        days = t.get("days_before_close", "?")
        signals = (t.get("signals") or "")[:60]
        blockers = (t.get("blockers") or "")[:60]
        lines.append(f"  {t.get('date', '?')} ({days}d before close): {prob}% | {signals} | {blockers}")

    return "\n".join(lines)
