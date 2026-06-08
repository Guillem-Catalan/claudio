"""Build system prompt for briefing generation, adapted to meeting type."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "briefing"

MEETING_TYPES = ("first_demo", "follow_up", "meddic_review", "pricing", "closing", "ad_hoc")

STAGE_TO_TYPE = {
    "Factorial Project Alignment started": "first_demo",
    "FPA": "first_demo",
    "Demo Booked": "first_demo",
    "Meeting Booked": "first_demo",
    "Meeting scheduled": "first_demo",
    "Product Alignment": "first_demo",
    "Discovery": "first_demo",
    "MEDDPICC Criteria Validation": "meddic_review",
    "Economical Allignment": "pricing",
    "Economical Alignment": "pricing",
    "Pricing and Packaging": "pricing",
    "Contract Sent": "closing",
}


def detect_meeting_type(deal_stage: str | None) -> str:
    if not deal_stage:
        return "follow_up"
    return STAGE_TO_TYPE.get(deal_stage, "follow_up")


def build_prompt(meeting_type: str) -> str:
    if meeting_type not in MEETING_TYPES:
        meeting_type = "follow_up"

    base = (_PROMPTS_DIR / "base.txt").read_text(encoding="utf-8")
    type_file = _PROMPTS_DIR / f"{meeting_type}.txt"

    if type_file.exists():
        type_prompt = type_file.read_text(encoding="utf-8")
        return f"{base}\n\n{type_prompt}"

    return base
