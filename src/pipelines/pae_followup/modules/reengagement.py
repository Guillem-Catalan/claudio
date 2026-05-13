"""
Module: reengagement (CONDITIONAL — stalled deals)
Output: Slack text — re-engagement sequence with cadence and messaging.
"""


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]
    deal_stage = data["deal"].get("deal_stage", "?")

    lines = [f"*Plan de re-engagement — {company}*"]
    lines.append(f"Stage actual: {deal_stage}")
    lines.append("")

    reason = section_data.get("stall_reason", "")
    if reason:
        lines.append(f"*Por qué se paró:* {reason}")
        lines.append("")

    sequence = section_data.get("sequence", [])
    if sequence:
        lines.append("*Secuencia:*")
        for i, step in enumerate(sequence, 1):
            day = step.get("day", f"Día {i}")
            channel = step.get("channel", "")
            action = step.get("action", "")
            lines.append(f"{i}. [{day}] {channel} — {action}")
        lines.append("")

    avoid = section_data.get("avoid", [])
    if avoid:
        lines.append("*No hacer:*")
        for item in avoid:
            lines.append(f"• {item}")
        lines.append("")

    triggers = section_data.get("trigger_events", "")
    if triggers:
        lines.append(f"_Trigger events a monitorizar: {triggers}_")

    return {
        "type": "text",
        "text": "\n".join(lines).strip(),
        "emoji": ":hourglass_flowing_sand:",
        "title": "Plan de re-engagement",
    }
