import json


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def _extract_red_flags(flags) -> list[str]:
    if not flags or not isinstance(flags, list):
        return []
    valid = {"BANT_3_MISSING", "NO_ECONOMIC_BUYER", "FORECAST_RED", "PARTNER_LEVERAGE_1"}
    return [f.get("type") for f in flags if isinstance(f, dict) and f.get("type") in valid]


def parse(response_text: str, role: str) -> dict:
    raw = json.loads(_strip_markdown(response_text))

    discovery = raw.get("discovery_depth") or {}
    topics = discovery.get("topics_covered")
    if isinstance(topics, list):
        topics = ", ".join(topics)

    resumen = raw.get("resumen") or {}

    result = {
        "win_rate_score": raw.get("win_rate_score"),
        "forecast_flag": raw.get("forecast_flag"),
        "partner_leverage_score": raw.get("partner_leverage_score"),
        "lead_temperature": raw.get("lead_temperature"),
        "discovery_level": discovery.get("level_reached"),
        "discovery_topics": topics,
        "discovery_breakdown": discovery.get("discovery_breakdown"),
        "red_flags_fired": _extract_red_flags(raw.get("red_flags")),
        "improvement_items_json": json.dumps(
            raw.get("improvement_items", []), ensure_ascii=False
        ),
        "deal_context": raw.get("deal_context") or resumen.get("deal_context"),
        "deal_status": raw.get("deal_status") or resumen.get("deal_status"),
        "biggest_gap": raw.get("biggest_gap") or resumen.get("biggest_gap"),
        "next_call_objective": raw.get("next_call_objective") or resumen.get("next_call_objective"),
        "tl_note": raw.get("tl_note") or resumen.get("tl_note"),
        "top_coaching_flag": raw.get("top_coaching_flag"),
        "next_action_rep": raw.get("next_action_rep"),
        "hard_question": raw.get("hard_question"),
        "objections": raw.get("objections"),
        "rep_strengths": raw.get("rep_strengths"),
        "buying_signals": raw.get("buying_signals"),
        "blockers": raw.get("blockers"),
        "tag_validation": raw.get("tag_validation"),
    }

    if role == "PBD":
        bant = raw.get("bant") or {}
        for pillar in ("budget", "authority", "need", "timing"):
            p = bant.get(pillar) or {}
            result[f"bant_{pillar}_status"] = p.get("status")
            result[f"bant_{pillar}_confidence"] = p.get("confidence")
            result[f"bant_{pillar}_evidence"] = p.get("evidence")

        script = raw.get("script_compliance") or {}
        result["script_opener"] = script.get("opener")
        result["script_industry_pivot"] = script.get("industry_pivot")
        result["script_close"] = script.get("close")
        result["two_slot_close"] = script.get("two_slot_close", False)

    elif role == "PAE":
        meddic = raw.get("meddic") or {}
        for pillar in ("metrics", "economic_buyer", "decision_criteria",
                       "decision_process", "champion", "competition"):
            p = meddic.get(pillar) or {}
            result[f"meddic_{pillar}_status"] = p.get("status")
            result[f"meddic_{pillar}_confidence"] = p.get("confidence")
            result[f"meddic_{pillar}_evidence"] = p.get("evidence")

    return result
