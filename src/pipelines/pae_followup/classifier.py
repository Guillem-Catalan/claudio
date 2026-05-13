"""
Classify a deal into strategy (active / stalled / closed) and subtype.

Level 1: deterministic — based on deal_stage.
Level 2: Claude classifier — determines subtype from audit + front_deals context.
"""

import json
import re
from pathlib import Path

from src.integrations.claude import analyze

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "pae_followup"

CLOSED_STAGES = {
    "closed lost", "closed won", "opportunity lost", "opportunity lost ",
    "closed pending payment", "closed won - finance only", "nurturing",
    "sales nurturing", "long nurturing", "hot nurturing",
}

STALLED_STAGES = {"on hold", "to reschedule"}

WON_STAGES = {"closed won", "closed won - finance only", "closed pending payment"}


def _level1(deal_stage: str) -> str:
    stage = (deal_stage or "").strip().lower()
    if stage in CLOSED_STAGES:
        return "closed"
    if stage in STALLED_STAGES:
        return "stalled"
    return "active"


def _is_won(deal_stage: str) -> bool:
    return (deal_stage or "").strip().lower() in WON_STAGES


def _load_classifier_prompt() -> str:
    return (_PROMPTS_DIR / "classifier.txt").read_text(encoding="utf-8")


def _parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def classify(data: dict) -> dict:
    """
    Returns {"strategy": str, "subtype": str, "is_won": bool, "reasoning": str}.
    """
    deal = data["deal"]
    deal_stage = deal.get("deal_stage") or ""

    strategy = _level1(deal_stage)
    is_won = _is_won(deal_stage)

    system_prompt = _load_classifier_prompt()

    user_prompt = (
        f"deal_stage: {deal_stage}\n"
        f"strategy: {strategy}\n"
        f"is_won: {is_won}\n\n"
    )

    pae_audit = data.get("pae_audit") or {}
    if pae_audit:
        user_prompt += "PAE AUDIT DATA:\n"
        for key in (
            "win_rate_score", "engagement", "objections", "buying_signals",
            "blockers", "red_flags_fired", "meddic_metrics_status",
            "meddic_economic_buyer_status", "meddic_decision_criteria_status",
            "meddic_decision_process_status", "meddic_champion_status",
            "meddic_competition_status", "next_action_rep", "biggest_gap",
        ):
            val = pae_audit.get(key)
            if val:
                user_prompt += f"  {key}: {val}\n"

    front_snapshot = data.get("front_deals_snapshot") or {}
    if front_snapshot:
        user_prompt += "\nFRONT DEALS SNAPSHOT:\n"
        for key in (
            "deal_summary", "objections", "buyer_signals", "live_blockers",
            "improvements", "deal_strengths", "next_step", "close_probability",
            "claudio_forecast",
        ):
            val = front_snapshot.get(key)
            if val:
                user_prompt += f"  {key}: {val}\n"

    deal_context = data.get("deal_context") or ""
    if deal_context:
        user_prompt += f"\nDEAL CONTEXT (truncated):\n{deal_context[:3000]}\n"

    raw = analyze(system_prompt, user_prompt, max_tokens=500)
    result = _parse_response(raw)

    result["strategy"] = strategy
    result["is_won"] = is_won

    return result
