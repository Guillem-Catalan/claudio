"""
Module: second_demo (CONDITIONAL)
Output: Slack text — agenda for second demo / technical deep dive.
"""


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]

    lines = [f"*Agenda segunda demo — {company}*", ""]

    for item in section_data.get("focus_areas", []):
        feature = item.get("feature", "")
        why = item.get("why", "")
        lines.append(f"• *{feature}* — {why}")

    lines.append("")

    invitees = section_data.get("invite", [])
    if invitees:
        lines.append("*Quién invitar:*")
        for person in invitees:
            lines.append(f"• {person}")
        lines.append("")

    objective = section_data.get("objective", "")
    if objective:
        lines.append(f"_Objetivo: {objective}_")

    duration = section_data.get("suggested_duration", "")
    if duration:
        lines.append(f"_Duración sugerida: {duration}_")

    return {
        "type": "text",
        "text": "\n".join(lines).strip(),
        "emoji": ":repeat:",
        "title": "Agenda segunda demo / deep dive",
    }
