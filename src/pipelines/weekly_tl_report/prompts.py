"""Prompt builders for weekly TL report synthesis."""


def build_activity_synthesis(pae_name: str, meetings: list[dict], week_start, week_end) -> tuple[str, str]:
    system_prompt = (
        "Eres un analista de Revenue Intelligence que genera weekly activity digests para Team Leads de ventas B2B SaaS. "
        "Tu trabajo es sintetizar las reuniones de la semana de un PAE, destacando patrones y coaching.\n\n"
        "Contexto: Factorial vende HR software a través de partners (Santander, Telefónica, TIM). "
        "El TL usa este digest para preparar 1:1s y detectar áreas de mejora.\n\n"
        "Responde ÚNICAMENTE con un JSON válido, sin markdown, sin prose."
    )

    event_blocks = []
    for m in meetings:
        ev = m.get("evaluation", {}) or {}
        deal = m.get("deal", {})
        block = (
            f"## {m.get('deal_name', '?')} [{m['meeting_type'].upper()}]\n"
            f"- Fecha: {m.get('meeting_start', '?')[:16]}\n"
            f"- Stage: {m.get('deal_stage', '?')}\n"
            f"- MRR: {m.get('amount', '?')}€\n"
            f"- Outcome: {m.get('outcome', '?')}\n"
            f"- Quality score: {ev.get('quality_score', '?')}/10\n"
            f"- Summary: {(ev.get('meeting_summary') or '-')[:300]}\n"
            f"- Signals: {(ev.get('signals') or '-')[:200]}\n"
            f"- Coaching: {(ev.get('coaching_note') or '-')[:200]}\n"
            f"- Has transcript: {'Yes' if m.get('has_call') else 'No'}\n"
        )
        event_blocks.append(block)

    user_prompt = (
        f"PAE: {pae_name}\n"
        f"Semana: {week_start} → {week_end}\n"
        f"Total reuniones: {len(meetings)}\n\n"
        + "\n".join(event_blocks)
        + "\n\n"
        "Genera el siguiente JSON:\n"
        "{\n"
        '  "summary": "Resumen ejecutivo (3 frases máx). Destaca: volumen actividad, quality scores, deals más relevantes, patrón principal.",\n'
        '  "events": [\n'
        "    {\n"
        '      "deal_name": "nombre",\n'
        '      "what_happened": "1 frase de qué pasó",\n'
        '      "deal_impact": "1 frase del impacto en el deal",\n'
        '      "quality": 7\n'
        "    }\n"
        "  ],\n"
        '  "coaching": [\n'
        '    "1. Título: observación concreta basada en las reuniones de esta semana"\n'
        "  ]\n"
        "}\n\n"
        "REGLAS:\n"
        "- Ordena events cronológicamente.\n"
        "- Máximo 4 coaching points.\n"
        "- Coaching basado en patrones reales de esta semana, no genéricos.\n"
        "- Si quality_score < 5 en algún meeting, destacarlo.\n"
    )

    return system_prompt, user_prompt


def build_pipeline_review(pae_name: str, qualified: list[dict]) -> tuple[str, str]:
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
        '  "summary": "Resumen ejecutivo para el TL (3-4 frases).",\n'
        '  "deals": [\n'
        "    {\n"
        '      "deal_name": "nombre exacto del deal",\n'
        '      "context": "2-3 frases: quién es, qué ha pasado, qué bloquea/acelera.",\n'
        '      "signals_top3": ["señal 1", "señal 2", "señal 3"],\n'
        '      "blockers_top3": ["blocker 1", "blocker 2", "blocker 3"],\n'
        '      "tl_action": "Acción concreta: qué hacer, con quién, cuándo."\n'
        "    }\n"
        "  ],\n"
        '  "patrones": [\n'
        '    "1. Título: descripción + acción coaching"\n'
        "  ]\n"
        "}\n\n"
        "REGLAS:\n"
        "- Ordena deals por MRR descendente.\n"
        "- En tl_action, sé específico: nombre, acción, timing.\n"
        "- Máximo 5 patrones.\n"
    )

    return system_prompt, user_prompt
