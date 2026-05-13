"""Generate EB assessment inline when no snapshot exists."""

import json

from src.integrations.claude import analyze

SYSTEM_PROMPT = """\
Eres un analista de ventas B2B SaaS. Tu tarea es evaluar el Economic Buyer de un deal
a partir del historial completo de interacciones.

Devuelve exactamente este JSON y nada más:

{
  "E_accumulate": "...",
  "E_score": 0
}

E_accumulate: Genera exactamente 2 frases en este orden fijo:
Frase 1 — Lo que se sabe: quién es el Economic Buyer identificado, si está confirmado o solo intuido,
y qué nivel de acceso o contacto directo se ha tenido con él.
Frase 2 — Estado: si el Economic Buyer está completamente validado, confirmarlo explícitamente.
Si no, indicar qué falta por conseguir (acceso directo, confirmación de presupuesto, implicación
en la decisión, etc.)
Sin títulos, sin bullets, solo las 2 frases como texto corrido. Máximo 35 palabras por frase.
Basarse únicamente en evidencia explícita del contexto del deal, no inferir nada no mencionado.

E_score: Número entero del 1 al 10. Evalúa en orden:
¿Se ha identificado quién es el Economic Buyer en alguna comunicación del deal? Si no → score máximo 3.
¿Se ha tenido contacto directo con el Economic Buyer en alguna comunicación? Si no → score máximo 5.
¿El Economic Buyer ha confirmado que hay presupuesto disponible? Si no → score máximo 7.
¿El Economic Buyer está activamente involucrado en el proceso de decisión y ha dado señales claras
de avanzar? Si no → score máximo 9. Si sí → score 10.
Dentro de cada tramo, ajusta según cantidad y solidez de evidencias. Solo devolver el número."""


def generate_eb_assessment(deal_context: str, deal: dict) -> tuple[str, int | None]:
    user_prompt = (
        f"Deal: {deal.get('deal_name', '?')}\n"
        f"Stage: {deal.get('deal_stage', '?')}\n"
        f"MRR: {deal.get('amount', '?')}€\n"
        f"PAE: {deal.get('pae', 'Ninguno')}\n"
        f"PBD: {deal.get('pbd', 'Ninguno')}\n\n"
        f"HISTORIAL COMPLETO DEL DEAL:\n\n{deal_context}"
    )

    raw = analyze(SYSTEM_PROMPT, user_prompt, max_tokens=1000)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)
    text = parsed.get("E_accumulate") or ""
    score = parsed.get("E_score")
    if isinstance(score, (int, float)):
        score = int(score)
    else:
        score = None

    return text, score
