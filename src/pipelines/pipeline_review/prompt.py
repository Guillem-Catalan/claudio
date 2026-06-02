"""Build system + user prompt for TL pipeline review synthesis."""


def build(pae_name: str, qualified: list[dict]) -> tuple[str, str]:
    system_prompt = (
        "Eres un analista de Revenue Intelligence que prepara briefings para Team Leads de ventas B2B SaaS. "
        "Tu trabajo es analizar los deals avanzados de un PAE y generar: "
        "(1) un resumen ejecutivo para el TL, "
        "(2) por cada deal, una acción concreta que el TL puede tomar en el 1:1, "
        "(3) patrones recurrentes que el TL debería trabajar como coaching.\n\n"
        "Contexto: Factorial vende HR software a través de partners (Santander, Telefónica). "
        "El TL usa este briefing para preparar 1:1s y pipeline reviews semanales.\n\n"
        "Responde ÚNICAMENTE con un JSON válido, sin markdown, sin prose."
    )

    deal_blocks = []
    for q in qualified:
        d, s = q["deal"], q["snap"]
        block = (
            f"## {d.get('deal_name', '?')}\n"
            f"- Stage: {d.get('deal_stage', '?')}\n"
            f"- MRR: {d.get('amount', '?')}€\n"
            f"- Edad: {d.get('deal_age_days', '?')}d\n"
            f"- Probabilidad: {s.get('close_probability', '?')}%\n"
            f"- MEDDIC: M={s.get('m_score','?')} E={s.get('e_score','?')} "
            f"DC={s.get('dc_score','?')} DP={s.get('dp_score','?')} "
            f"I={s.get('i_score','?')} C={s.get('c_score','?')}\n"
            f"- Deal Summary: {s.get('deal_summary', '-')}\n"
            f"- Buyer Signals: {s.get('buyer_signals', '-')}\n"
            f"- Live Blockers: {s.get('live_blockers', '-')}\n"
            f"- Objections: {s.get('objections', '-')}\n"
            f"- Next Step: {s.get('next_step', '-')}\n"
            f"- Deal Strengths: {s.get('deal_strengths', '-')}\n"
        )
        deal_blocks.append(block)

    user_prompt = (
        f"PAE: {pae_name}\n"
        f"Deals avanzados con probabilidad >= 46%: {len(qualified)}\n\n"
        + "\n".join(deal_blocks)
        + "\n\n"
        "Genera el siguiente JSON:\n"
        "{\n"
        '  "summary": "Resumen ejecutivo para el TL (3-4 frases). '
        "Destaca el patrón principal, los deals más urgentes y la acción clave del 1:1.\",\n"
        '  "deals": [\n'
        "    {\n"
        '      "deal_name": "nombre exacto del deal",\n'
        '      "context": "Párrafo de 2-3 frases: quién es la empresa, qué ha pasado recientemente, '
        'qué está bloqueando o acelerando. Incluye nombres de personas clave y datos concretos.",\n'
        '      "signals_top3": ["señal 1 con cita si hay", "señal 2", "señal 3"],\n'
        '      "blockers_top3": ["blocker 1 específico", "blocker 2", "blocker 3"],\n'
        '      "tl_action": "Acción concreta que el TL puede tomar: qué hacer, con quién, cuándo, '
        'y qué se desbloquea. No genérico — específico al deal."\n'
        "    }\n"
        "  ],\n"
        '  "patrones": [\n'
        '    "1. Título del patrón: descripción de qué se repite + acción concreta de coaching",\n'
        '    "2. ..."\n'
        "  ]\n"
        "}\n\n"
        "REGLAS:\n"
        "- Ordena deals por MRR descendente.\n"
        "- En context, usa datos del Deal Summary pero reescribe para el TL — no copies tal cual.\n"
        "- En signals_top3 y blockers_top3, prioriza las más relevantes para el TL, no las más genéricas.\n"
        "- En tl_action, sé específico: nombre de persona, acción, timing. El TL debe saber qué hacer sin leer más.\n"
        "- En patrones, busca temas que se repiten en 2+ deals. No repitas lo que ya dijiste por deal.\n"
        "- Máximo 5 patrones.\n"
    )

    return system_prompt, user_prompt
