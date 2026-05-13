"""
Module: objections (CONDITIONAL)
Output: Slack text — each objection with response angle + data.
"""


def render(section_data: dict, data: dict, brief: dict) -> dict:
    items = section_data.get("items", [])
    if not items:
        return None

    lines = []
    for i, obj in enumerate(items, 1):
        q = obj.get("objection", "")
        angle = obj.get("angle", "")
        evidence = obj.get("evidence", "")
        lines.append(f"*{i}. «{q}»*")
        lines.append(f"   Ángulo: {angle}")
        if evidence:
            lines.append(f"   Evidencia: {evidence}")
        lines.append("")

    return {
        "type": "text",
        "text": "\n".join(lines).strip(),
        "emoji": ":shield:",
        "title": "Objeciones detectadas + ángulos de respuesta",
    }
