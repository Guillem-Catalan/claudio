"""
Build the user prompt for atlas generation from raw HubSpot data.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_system_prompt() -> str:
    return (_PROMPTS_DIR / "atlas.txt").read_text(encoding="utf-8")


def format_company_info(company: dict) -> str:
    lines = []
    if company.get("name"):
        lines.append(f"Nombre: {company['name']}")
    if company.get("industry"):
        lines.append(f"Industria: {company['industry']}")
    if company.get("numberofemployees"):
        lines.append(f"Empleados: {company['numberofemployees']}")
    if company.get("annualrevenue"):
        lines.append(f"Revenue anual: {company['annualrevenue']}")
    if company.get("country"):
        lines.append(f"País: {company['country']}")
    if company.get("city"):
        lines.append(f"Ciudad: {company['city']}")
    if company.get("website"):
        lines.append(f"Web: {company['website']}")
    if company.get("description"):
        lines.append(f"Descripción: {company['description']}")
    return "\n".join(lines) if lines else "(sin información de empresa)"


def format_deals_breakdown(deals: list[dict]) -> str:
    if not deals:
        return "(sin deals asociados)"

    lines = []
    for d in deals:
        status = "GANADO" if d["is_closed_won"] == "true" else ("PERDIDO/CERRADO" if d["is_closed"] == "true" else "ACTIVO")
        parts = [
            f"- {d['name']}",
            f"  Stage: {d['stage']}",
            f"  Estado: {status}",
        ]
        if d["amount"]:
            parts.append(f"  Amount: {d['amount']}")
        if d["create_date"]:
            parts.append(f"  Creado: {d['create_date']}")
        if d["close_date"]:
            parts.append(f"  Cierre: {d['close_date']}")
        if d["forecast_category"]:
            parts.append(f"  Forecast: {d['forecast_category']}")
        if d["owner"]:
            parts.append(f"  Owner: {d['owner']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def format_contacts_breakdown(contacts: list[dict]) -> str:
    if not contacts:
        return "(sin contactos asociados)"

    lines = []
    for c in contacts:
        parts = [f"- {c['name']}"]
        if c["jobtitle"]:
            parts.append(f"  Cargo: {c['jobtitle']}")
        if c["email"]:
            parts.append(f"  Email: {c['email']}")
        if c["phone"]:
            parts.append(f"  Teléfono: {c['phone']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def build_user_prompt(company_info: str, deals_breakdown: str, contacts_breakdown: str,
                      n_deals: int, n_contacts: int) -> str:
    return (
        f"## Empresa\n{company_info}\n\n"
        f"## Deals ({n_deals} total)\n{deals_breakdown}\n\n"
        f"## Contactos ({n_contacts} total)\n{contacts_breakdown}"
    )
