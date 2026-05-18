"""Build Claude prompt for weekly demo coaching synthesis."""

from datetime import date, timedelta

SYSTEM_PROMPT = (
    "Eres un coach semanal de demos de ventas B2B SaaS para Factorial. "
    "Recibes las evaluaciones individuales de todas las demos que un PAE ha hecho "
    "en una semana, junto con el contexto previo de cada deal (emails, notas, calls PBD). "
    "Tu trabajo es sintetizar patrones, identificar fortalezas y gaps comunes, "
    "evaluar el estado BANT de cada deal basándote en toda la comunicación previa, "
    "y dar coaching accionable.\n\n"
    "Responde SIEMPRE en español. Sé directo y concreto — nada de fluff."
)

OUTPUT_SPEC = """\
Devuelve un JSON con esta estructura exacta:

{
  "meddic_intro_note": "1-2 frases contextuales sobre el estado general MEDDIC de las demos esta semana. Max 50 palabras.",
  "m_status": "rojo|ámbar|verde",
  "m_text": "Síntesis de Metrics en las demos de la semana. 2 frases max, 35 palabras/frase.",
  "e_status": "rojo|ámbar|verde",
  "e_text": "Síntesis de Economic Buyer. 2 frases max.",
  "dc_status": "rojo|ámbar|verde",
  "dc_text": "Síntesis de Decision Criteria. 2 frases max.",
  "dp_status": "rojo|ámbar|verde",
  "dp_text": "Síntesis de Decision Process. 2 frases max.",
  "i_status": "rojo|ámbar|verde",
  "i_text": "Síntesis de Identify Pain. 2 frases max.",
  "c_status": "rojo|ámbar|verde",
  "c_text": "Síntesis de Champion. 2 frases max.",
  "bant_per_deal": [
    {
      "deal": "nombre exacto del deal",
      "budget": "Confirmed|Partial|Missing",
      "authority": "Confirmed|Partial|Missing",
      "need": "Confirmed|Partial|Missing",
      "timing": "Confirmed|Partial|Missing"
    }
  ],
  "buyer_signals": [{"deal": "nombre del deal", "signals": ["señal concreta 1", "señal concreta 2"]}],
  "objections": [{"category": "categoría (precio, competencia, timing, etc.)", "text": "objeción concreta"}],
  "improvements": [{"title": "Título corto (3-5 palabras)", "text": "Descripción accionable. 1-2 frases."}],
  "pbd_handover_note": "Valoración de la calidad del handover PBD → PAE basada en el BANT previo y el contexto pre-demo. 2-3 frases."
}

Reglas:
- status: "rojo" si hay gaps críticos repetidos, "ámbar" si hay progreso parcial, "verde" si la ejecución es buena
- bant_per_deal: evalúa el BANT basándote en TODA la comunicación previa a la demo (emails, notas, calls PBD, calls anteriores del PAE). "Confirmed" = se abordó explícitamente con evidencia clara, "Partial" = se tocó pero sin profundidad, "Missing" = no se abordó. Un item por cada deal.
- buyer_signals: señales reales extraídas de las demos, AGRUPADAS por deal. Todas las señales del mismo deal en un solo array.
- objections: agrupadas por categoría, no por deal
- improvements: 5-7 items, enfocados en PATRONES que se repiten entre demos, no issues puntuales
- pbd_handover_note: valora si el PBD dejó un BANT sólido o si el PAE tuvo que empezar de cero, usando el contexto previo disponible
- NO incluir scores numéricos en ningún campo
"""


def _format_date(val) -> str:
    return str(val)[:10] if val else "—"


def _truncate_context(ctx: str, max_chars: int = 1500) -> str:
    if not ctx or len(ctx) <= max_chars:
        return ctx or ""
    return ctx[:max_chars] + "\n... (truncado)"


def build(
    pae_name: str,
    pae_email: str,
    week_start: date,
    week_end: date,
    audit_rows: list[dict],
    deals_data: dict[str, dict],
) -> tuple[str, str]:
    week_range = f"{week_start.isoformat()} → {(week_end - timedelta(days=1)).isoformat()}"

    lines = [
        f"=== PAE: {pae_name} ({pae_email}) · Semana {week_range} ===",
        "",
    ]

    for i, row in enumerate(audit_rows, 1):
        deal_name = row.get("deal_name") or "?"
        demo_date = _format_date(row.get("demo_date"))
        amount = row.get("amount")
        mrr = f"€{float(amount):,.0f}" if amount is not None else "?"
        deal_ref = row.get("deal_ref")
        deal = deals_data.get(deal_ref, {}) if deal_ref else {}
        stage = deal.get("deal_stage") or row.get("deal_stage") or "?"
        age = deal.get("deal_age_days") or "?"

        lines += [
            f"--- DEMO {i}: {deal_name} ({demo_date}) ---",
            f"MRR: {mrr} · Stage: {stage} · Age: {age}d",
            f"Demo Summary: {row.get('demo_summary') or '—'}",
            f"M: {row.get('m_accumulate') or '—'}",
            f"E: {row.get('e_accumulate') or '—'}",
            f"DC: {row.get('dc_accumulate') or '—'}",
            f"DP: {row.get('dp_accumulate') or '—'}",
            f"I: {row.get('i_accumulate') or '—'}",
            f"C: {row.get('c_accumulate') or '—'}",
            f"Objections: {row.get('objections') or '—'}",
            f"Buyer signals: {row.get('buyer_signals') or '—'}",
            f"Improvements: {row.get('improvements') or '—'}",
            f"Strengths: {row.get('deal_strengths') or '—'}",
            "",
        ]

    lines.append("=== CONTEXTO PRE-DEMO POR DEAL (emails, notas, calls PBD, etc.) ===")
    lines.append("Usa este contexto para evaluar el BANT de cada deal en bant_per_deal.")
    lines.append("")
    seen_deals = set()
    for row in audit_rows:
        deal_ref = row.get("deal_ref")
        if not deal_ref or deal_ref in seen_deals:
            continue
        seen_deals.add(deal_ref)
        deal_name = row.get("deal_name") or "?"
        deal = deals_data.get(deal_ref, {})
        ctx = deal.get("deal_context") or ""
        lines.append(f'--- Deal: {deal_name} ---')
        if ctx.strip():
            lines.append(_truncate_context(ctx))
        else:
            lines.append("(Sin comunicación previa registrada)")
        lines.append("")

    lines += ["", "=== OUTPUT SPEC ===", OUTPUT_SPEC]

    return SYSTEM_PROMPT, "\n".join(lines)
