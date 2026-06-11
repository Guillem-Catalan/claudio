"""
Compile deal trajectory when a deal closes (won/lost).
Called by Run Deals or by trigger. Stores the full history in deal_trajectories.
"""

import json
import re
from src.db.client import supabase
from src.integrations.claude import analyze
from src.config import TEAMS


def _get_team(pae_email: str) -> str:
    for team_name, team in TEAMS.items():
        if pae_email in team.get("pae", set()):
            return team_name
    return ""


def _resolve_pae_email(pae_name: str) -> str:
    if not pae_name:
        return ""
    resp = (
        supabase.table("calls")
        .select("owner_email")
        .ilike("owner_nombre", f"%{pae_name.split()[0]}%")
        .not_.is_("owner_email", "null")
        .limit(1)
        .execute()
    )
    return resp.data[0]["owner_email"] if resp.data else ""


def compile_trajectory(deal_uuid: str) -> dict | None:
    """Compile full trajectory for a closed deal and store in deal_trajectories."""

    deal_resp = supabase.table("deals").select("*").eq("id", deal_uuid).maybe_single().execute()
    if not deal_resp.data:
        return None
    d = deal_resp.data
    stage = (d.get("deal_stage") or "").lower()

    if "closed won" in stage or "closed won - finance only" in stage:
        outcome = "won"
    elif "closed lost" in stage or "opportunity lost" in stage:
        outcome = "lost"
    elif "on hold" in stage:
        outcome = "on_hold"
    else:
        return None

    existing = supabase.table("deal_trajectories").select("id").eq("deal_id", deal_uuid).limit(1).execute()
    if existing.data:
        return None

    snap_resp = (
        supabase.table("front_deal_snapshots")
        .select("snapshot_date, close_probability, m_score, e_score, dc_score, dp_score, i_score, c_score, comp_score, buyer_signals, live_blockers, next_step, deal_assessment, action_signal")
        .eq("deal_id", deal_uuid)
        .order("snapshot_date")
        .execute()
    )
    snapshots = snap_resp.data or []

    close_date = d.get("close_date")
    trajectory = []
    for s in snapshots:
        days_before = None
        if close_date and s.get("snapshot_date"):
            from datetime import date as dt_date
            try:
                cd = dt_date.fromisoformat(str(close_date))
                sd = dt_date.fromisoformat(str(s["snapshot_date"]))
                days_before = (cd - sd).days
            except (ValueError, TypeError):
                pass

        trajectory.append({
            "date": s["snapshot_date"],
            "days_before_close": days_before,
            "probability": s.get("close_probability"),
            "meddic": {
                "m": s.get("m_score"), "e": s.get("e_score"),
                "dc": s.get("dc_score"), "dp": s.get("dp_score"),
                "i": s.get("i_score"), "c": s.get("c_score"),
                "comp": s.get("comp_score"),
            },
            "signals": (s.get("buyer_signals") or "")[:200],
            "blockers": (s.get("live_blockers") or "")[:200],
            "next_step": (s.get("next_step") or "")[:200],
            "assessment": (s.get("deal_assessment") or "")[:200],
        })

    stage_dates = {}
    for col in ("dist_demo_booked_entered", "dist_product_alignment_entered",
                "dist_meddpicc_validation_entered", "dist_pricing_and_packaging_entered",
                "dist_closed_won_entered", "dist_closed_lost_entered"):
        val = d.get(col)
        if val:
            key = col.replace("dist_", "").replace("_entered", "")
            stage_dates[key] = str(val)

    call_resp = supabase.table("calls").select("id").eq("deal_id", deal_uuid).execute()
    meeting_resp = supabase.table("deal_meetings").select("id").eq("deal_id", deal_uuid).execute()

    interactions = {
        "total_calls": d.get("numero_de_calls") or 0,
        "total_emails": d.get("numero_de_emails") or 0,
        "total_notes": d.get("numero_de_notas") or 0,
        "total_meetings": d.get("numero_de_meetings") or 0,
        "modjo_calls": len(call_resp.data or []),
        "hs_meetings": len(meeting_resp.data or []),
    }

    pae_email = _resolve_pae_email(d.get("pae") or "")
    team = _get_team(pae_email) if pae_email else ""

    lessons = _generate_lessons(d, trajectory, outcome)

    row = {
        "deal_id": deal_uuid,
        "outcome": outcome,
        "amount": d.get("amount"),
        "deal_age_days": d.get("deal_age_days"),
        "pae": d.get("pae"),
        "pbd": d.get("pbd"),
        "team": team,
        "pipeline_name": d.get("pipeline_name"),
        "closed_lost_reason": d.get("closed_lost_reason"),
        "close_date": d.get("close_date"),
        "trajectory": json.dumps(trajectory),
        "stage_dates": json.dumps(stage_dates),
        "interactions": json.dumps(interactions),
        "lessons": json.dumps(lessons),
    }
    row = {k: v for k, v in row.items() if v is not None}

    supabase.table("deal_trajectories").insert(row).execute()
    return row


def _generate_lessons(deal: dict, trajectory: list[dict], outcome: str) -> list[str]:
    """Use Claude to extract lessons from a completed deal trajectory."""
    if not trajectory:
        return []

    deal_name = deal.get("deal_name", "?")
    amount = deal.get("amount", "?")
    age = deal.get("deal_age_days", "?")
    pae = deal.get("pae", "?")
    lost_reason = deal.get("closed_lost_reason", "")

    traj_summary = []
    for t in trajectory[-10:]:
        traj_summary.append(
            f"  {t['date']} ({t.get('days_before_close', '?')}d before close): "
            f"prob={t.get('probability', '?')}% | "
            f"signals: {t.get('signals', '-')[:80]} | "
            f"blockers: {t.get('blockers', '-')[:80]}"
        )

    context_snippet = (deal.get("deal_context") or "")[-3000:]

    system = (
        "Eres un analista de Revenue Intelligence. Analiza la trayectoria de un deal cerrado "
        "y extrae 3-5 lecciones concretas que sirvan para predecir deals futuros similares. "
        "Responde SOLO con un JSON array de strings. Sin markdown."
    )
    user = (
        f"Deal: {deal_name} | €{amount} | {age} días | PAE: {pae} | Outcome: {outcome}\n"
        f"Lost reason: {lost_reason}\n\n"
        f"Trayectoria (últimos 10 snapshots):\n" + "\n".join(traj_summary) + "\n\n"
        f"Últimas interacciones:\n{context_snippet[:2000]}\n\n"
        "Extrae 3-5 lecciones concretas. Cada lección debe ser específica y accionable, "
        "no genérica. Formato: qué señal había, qué pasó, qué debería hacer Claudio "
        "diferente la próxima vez que vea una señal similar."
    )

    try:
        raw = analyze(system, user, max_tokens=1000)
        text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())
    except Exception:
        return [f"Deal {outcome}: {deal_name}, €{amount}, {age}d, PAE: {pae}"]
