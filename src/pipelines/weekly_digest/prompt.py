"""Build system + user prompt for weekly activity digest."""

from datetime import date


SYSTEM = (
    "Eres un analista de Revenue Intelligence que genera weekly activity digests para Team Leads de ventas B2B SaaS. "
    "Recibes todas las interacciones de un PAE durante la semana (calls, demos, meetings) con su análisis de audit. "
    "Tu trabajo es generar un JSON conciso con: (1) resumen ejecutivo, (2) análisis por interacción, (3) coaching semanal.\n\n"
    "Responde ÚNICAMENTE con JSON válido, sin markdown ni prose."
)


def build(
    pae_name: str,
    events: list[dict],
    week_start: date,
    week_end: date,
) -> tuple[str, str]:

    event_blocks = []
    for i, e in enumerate(events):
        block = f"## Interacción {i + 1}: {e['type']}\n"
        block += f"- Fecha: {e['dt'][:16]}\n"
        block += f"- Deal: {e['deal_name']}\n"
        block += f"- Stage: {e.get('deal_stage', '?')}\n"
        block += f"- MRR: {e.get('amount', '?')}€\n"
        block += f"- Probabilidad: {e.get('prob', '?')}%\n"
        if e.get("duration_min"):
            block += f"- Duración: {e['duration_min']}min\n"
        if e.get("audit_context"):
            block += f"- Qué pasó (audit): {e['audit_context'][:500]}\n"
        if e.get("signals"):
            block += f"- Señales: {e['signals'][:300]}\n"
        if e.get("blockers"):
            block += f"- Blockers: {e['blockers'][:300]}\n"
        if e.get("next_step"):
            block += f"- Next step: {e['next_step'][:300]}\n"
        if e.get("deal_snapshot"):
            block += f"- Deal snapshot: {e['deal_snapshot'][:300]}\n"
        if e.get("title"):
            block += f"- Título meeting: {e['title']}\n"
        if e.get("outcome"):
            block += f"- Outcome: {e['outcome']}\n"
        event_blocks.append(block)

    week_end_fri = week_end
    user = (
        f"PAE: {pae_name}\n"
        f"Semana: {week_start.isoformat()} → {week_end_fri.isoformat()} (lunes a viernes)\n"
        f"Total interacciones: {len(events)}\n\n"
        + "\n".join(event_blocks)
        + "\n\n"
        "Genera este JSON:\n"
        "{\n"
        '  "summary": "3 frases máximo. Qué fue lo más importante, qué no se tocó, qué hacer en el 1:1.",\n'
        '  "events": [\n'
        "    {\n"
        '      "deal_name": "nombre exacto",\n'
        '      "what_happened": "1-2 frases cortas. Qué pasó, con quién, dato clave. Máximo 30 palabras.",\n'
        '      "deal_impact": "1 frase de máximo 15 palabras. Cómo mueve el deal.",\n'
        '      "signals_top3": ["máximo 10 palabras cada una, con cita si hay"],\n'
        '      "blockers_top3": ["máximo 10 palabras cada uno"],\n'
        '      "next_step": "1 frase: quién + qué + cuándo. Máximo 20 palabras."\n'
        "    }\n"
        "  ],\n"
        '  "coaching": [\n'
        '    "1. Título: 1 frase de acción. Máximo 25 palabras.",\n'
        '    "2. ..."\n'
        "  ]\n"
        "}\n\n"
        "REGLAS:\n"
        "- SÉ BREVE. El TL escanea esto en 2 minutos. Menos texto = más útil.\n"
        "- Ordena events cronológicamente.\n"
        "- En what_happened, NO repitas el snapshot. Cuenta solo qué pasó EN ESTA interacción.\n"
        "- En deal_impact, el TL debe entenderlo en 3 segundos.\n"
        "- Señales y blockers: bullets cortos, no frases completas.\n"
        "- Coaching: máximo 4 puntos. Menciona deals importantes SIN actividad esta semana.\n"
        "- Para meetings sin audit, 1 frase de contexto del deal.\n"
    )

    return SYSTEM, user
