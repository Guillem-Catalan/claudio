"""
Forecast V2: judgment-based monthly forecast using benchmark data.
Runs after snapshot in Run Deals Phase 5.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.intelligence.similarity import find_similar

_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "intelligence" / "forecast_v2.txt"


def run(deal_uuid: str, snapshot: dict, deal: dict) -> dict | None:
    """Generate forecast v2 for a deal using benchmark comparison."""

    deal_name = deal.get("deal_name", "?")
    deal_stage = deal.get("deal_stage", "?")
    amount = float(deal.get("amount") or 0)
    age = deal.get("deal_age_days") or 0
    pae = deal.get("pae") or deal.get("pbd") or "?"
    close_date_pae = deal.get("close_date") or "?"

    # 1. Get deal trajectory (all snapshots)
    snap_resp = (
        supabase.table("front_deal_snapshots")
        .select("snapshot_date, close_probability, m_score, e_score, dc_score, dp_score, i_score, c_score, buyer_signals, live_blockers, next_step, deal_assessment")
        .eq("deal_id", deal_uuid)
        .order("snapshot_date")
        .execute()
    )
    snapshots = snap_resp.data or []

    traj_lines = []
    for s in snapshots[-15:]:
        prob = s.get("close_probability", "?")
        signals = (s.get("buyer_signals") or "")[:80]
        blockers = (s.get("live_blockers") or "")[:80]
        traj_lines.append(
            f"  {s['snapshot_date']}: prob={prob}% | signals: {signals} | blockers: {blockers}"
        )
    trajectory_text = "\n".join(traj_lines) if traj_lines else "No previous snapshots."

    # 2. Get similar historical deals
    pae_email = ""
    from src.config import TEAMS
    for team_name, team in TEAMS.items():
        if any(pae.lower() in (e.split("@")[0].replace(".", " ").lower()) for e in team.get("pae", set())):
            team_name_resolved = team_name
            break
    else:
        team_name_resolved = None

    similar_won = find_similar(deal_stage, amount, age, team=team_name_resolved, outcome_filter="won", limit=5)
    similar_lost = find_similar(deal_stage, amount, age, team=team_name_resolved, outcome_filter="lost", limit=5)

    won_text = "\n\n".join(
        f"DEAL WON: €{s['amount'] or '?'} | {s['deal_age_days'] or '?'}d | PAE: {s['pae'] or '?'}\n"
        f"Trajectory:\n{s['trajectory_summary']}\n"
        f"Lessons: {'; '.join(s['lessons'][:3]) if s['lessons'] else 'None'}"
        for s in similar_won
    ) if similar_won else "No similar won deals in benchmark yet."

    lost_text = "\n\n".join(
        f"DEAL LOST ({s['closed_lost_reason'] or '?'}): €{s['amount'] or '?'} | {s['deal_age_days'] or '?'}d | PAE: {s['pae'] or '?'}\n"
        f"Trajectory:\n{s['trajectory_summary']}\n"
        f"Lessons: {'; '.join(s['lessons'][:3]) if s['lessons'] else 'None'}"
        for s in similar_lost
    ) if similar_lost else "No similar lost deals in benchmark yet."

    # 3. Get learned patterns
    pattern_resp = (
        supabase.table("learned_patterns")
        .select("pattern")
        .order("generated_at", desc=True)
        .limit(10)
        .execute()
    )
    patterns_text = "\n".join(
        f"• {p['pattern']}" for p in (pattern_resp.data or [])
    ) if pattern_resp.data else "No learned patterns yet."

    # 4. Get calibration errors
    current_month = date.today().strftime("%Y-%m")
    prev_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    cal_resp = (
        supabase.table("calibration_log")
        .select("deal_name, predicted_close_this_month, actual_outcome, error_analysis")
        .eq("month", prev_month)
        .limit(5)
        .execute()
    )
    calibration_text = "\n".join(
        f"• {c['deal_name']}: predicted={'close' if c['predicted_close_this_month'] else 'no close'}, "
        f"actual={c['actual_outcome']}, lesson: {c['error_analysis']}"
        for c in (cal_resp.data or [])
    ) if cal_resp.data else "No calibration data yet (first month)."

    # 5. Get recent deal_context (last interactions)
    ctx = (deal.get("deal_context") or "")[-5000:]

    # 6. Current snapshot data
    current_snap = (
        f"MEDDIC: M={snapshot.get('m_score','?')} E={snapshot.get('e_score','?')} "
        f"DC={snapshot.get('dc_score','?')} DP={snapshot.get('dp_score','?')} "
        f"I={snapshot.get('i_score','?')} C={snapshot.get('c_score','?')}\n"
        f"Probability v1: {snapshot.get('close_probability', '?')}%\n"
        f"Assessment: {(snapshot.get('deal_assessment') or '')[:300]}\n"
        f"Signals: {(snapshot.get('buyer_signals') or '')[:200]}\n"
        f"Blockers: {(snapshot.get('live_blockers') or '')[:200]}\n"
        f"Next step: {(snapshot.get('next_step') or '')[:200]}"
    )

    # 7. Build prompt
    prompt_template = _PROMPT_PATH.read_text()

    user_prompt = (
        f"## DEAL TO FORECAST\n"
        f"Name: {deal_name}\n"
        f"Stage: {deal_stage} | Amount: €{amount} | Age: {age} days | PAE: {pae}\n"
        f"PAE close_date: {close_date_pae}\n"
        f"Today: {date.today().isoformat()}\n"
        f"Current month: {current_month}\n\n"
        f"## CURRENT SNAPSHOT\n{current_snap}\n\n"
        f"## TRAJECTORY (last 15 snapshots)\n{trajectory_text}\n\n"
        f"## RECENT INTERACTIONS (last 5K chars)\n{ctx}\n\n"
        f"## SIMILAR DEALS THAT WON\n{won_text}\n\n"
        f"## SIMILAR DEALS THAT LOST\n{lost_text}\n\n"
        f"## LEARNED PATTERNS\n{patterns_text}\n\n"
        f"## CALIBRATION (last month errors)\n{calibration_text}\n\n"
        f"{prompt_template}"
    )

    system = (
        "Eres Claudio, un sistema de Revenue Intelligence que predice cuándo se cerrarán deals de ventas B2B SaaS. "
        "Tu trabajo es analizar un deal activo comparándolo con deals históricos similares y hacer una predicción "
        "de si se cerrará este mes, el siguiente, o más tarde. "
        "No uses fórmulas — lee el contexto real como lo haría un VP de Sales con 20 años de experiencia. "
        "Responde SOLO con un JSON válido. Sin markdown, sin prose."
    )

    try:
        raw = analyze(system, user_prompt, max_tokens=2000)
        text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text.strip())
        return result
    except Exception as e:
        print(f"  [forecast_v2] Failed: {e}")
        return None
