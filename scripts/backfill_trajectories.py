"""Backfill deal_trajectories for all closed deals with snapshots. No Claude calls (no lessons)."""

import json
import sys
from datetime import date as dt_date

from src.db.client import supabase
from src.config import TEAMS


def _get_team(pae_name: str) -> str:
    if not pae_name:
        return ""
    for team_name, team in TEAMS.items():
        for email in team.get("pae", set()):
            name = email.split("@")[0].replace(".", " ").title()
            if name.lower() in pae_name.lower() or pae_name.lower() in name.lower():
                return team_name
    return ""


def backfill(limit: int = 500):
    print(f"Backfilling trajectories (limit {limit}) ...")

    existing_resp = supabase.table("deal_trajectories").select("deal_id").execute()
    existing_ids = {r["deal_id"] for r in (existing_resp.data or [])}

    deals_resp = (
        supabase.table("deals")
        .select("id, deal_name, deal_stage, amount, deal_age_days, pae, pbd, close_date, "
                "pipeline_name, closed_lost_reason, numero_de_emails, numero_de_notas, "
                "numero_de_calls, numero_de_meetings, "
                "dist_demo_booked_entered, dist_product_alignment_entered, "
                "dist_meddpicc_validation_entered, dist_pricing_and_packaging_entered, "
                "dist_closed_won_entered, dist_closed_lost_entered")
        .in_("deal_stage", [
            "Closed Won", "Closed won", "Closed Won - Finance Only",
            "Closed Lost", "Closed lost", "Opportunity lost", "Opportunity Lost",
        ])
        .gte("close_date", "2026-01-01")
        .order("amount", desc=True)
        .limit(limit + len(existing_ids))
        .execute()
    )

    deals = [d for d in (deals_resp.data or []) if d["id"] not in existing_ids][:limit]
    print(f"  {len(deals)} deals to process")

    compiled = 0
    for i, d in enumerate(deals, 1):
        deal_id = d["id"]
        stage = (d.get("deal_stage") or "").lower()

        if "closed won" in stage or "finance only" in stage:
            outcome = "won"
        elif "closed lost" in stage or "opportunity lost" in stage:
            outcome = "lost"
        else:
            continue

        # Get snapshots
        snap_resp = (
            supabase.table("front_deal_snapshots")
            .select("snapshot_date, close_probability, m_score, e_score, dc_score, dp_score, "
                    "i_score, c_score, comp_score, buyer_signals, live_blockers, next_step, deal_assessment")
            .eq("deal_id", deal_id)
            .order("snapshot_date")
            .execute()
        )
        snapshots = snap_resp.data or []
        if not snapshots:
            continue

        close_date = d.get("close_date")
        trajectory = []
        for s in snapshots:
            days_before = None
            if close_date and s.get("snapshot_date"):
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
            })

        stage_dates = {}
        for col in ("dist_demo_booked_entered", "dist_product_alignment_entered",
                    "dist_meddpicc_validation_entered", "dist_pricing_and_packaging_entered",
                    "dist_closed_won_entered", "dist_closed_lost_entered"):
            val = d.get(col)
            if val:
                stage_dates[col.replace("dist_", "").replace("_entered", "")] = str(val)

        interactions = {
            "total_calls": d.get("numero_de_calls") or 0,
            "total_emails": d.get("numero_de_emails") or 0,
            "total_notes": d.get("numero_de_notas") or 0,
            "total_meetings": d.get("numero_de_meetings") or 0,
        }

        team = _get_team(d.get("pae") or "")

        row = {
            "deal_id": deal_id,
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
            "lessons": json.dumps([]),
        }
        row = {k: v for k, v in row.items() if v is not None}

        try:
            supabase.table("deal_trajectories").insert(row).execute()
            compiled += 1
            if compiled % 50 == 0:
                print(f"  [{compiled}/{len(deals)}] {d['deal_name'][:40]} ({outcome})")
        except Exception as e:
            print(f"  Error on {d['deal_name'][:40]}: {e}")

    print(f"\n  Done: {compiled} trajectories compiled.")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    backfill(limit)
