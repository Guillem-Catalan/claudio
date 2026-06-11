"""
Generate learned patterns from deal trajectories.
Run weekly to update the pattern database.
"""

import json
import re
from src.db.client import supabase
from src.integrations.claude import analyze


def generate_patterns():
    """Analyze all trajectories and generate/update learned patterns."""
    print("Generating learned patterns ...")

    traj_resp = supabase.table("deal_trajectories").select(
        "outcome, amount, deal_age_days, pae, team, closed_lost_reason, trajectory, lessons"
    ).order("created_at", desc=True).limit(200).execute()
    trajectories = traj_resp.data or []

    if len(trajectories) < 10:
        print(f"  Only {len(trajectories)} trajectories — need at least 10 to generate patterns.")
        return

    won = [t for t in trajectories if t["outcome"] == "won"]
    lost = [t for t in trajectories if t["outcome"] == "lost"]

    all_lessons = []
    for t in trajectories:
        lessons = t.get("lessons")
        if isinstance(lessons, str):
            try: lessons = json.loads(lessons)
            except: lessons = []
        all_lessons.extend(lessons or [])

    lost_reasons = {}
    for t in lost:
        r = t.get("closed_lost_reason") or "Unknown"
        lost_reasons[r] = lost_reasons.get(r, 0) + 1

    system = (
        "Eres un analista de Revenue Intelligence. Analiza las lecciones aprendidas de deals "
        "cerrados (ganados y perdidos) y genera patrones concretos que sirvan para predecir "
        "deals futuros. Responde SOLO con un JSON array de objects. Sin markdown."
    )

    user = (
        f"Benchmark: {len(won)} deals ganados, {len(lost)} deals perdidos.\n\n"
        f"Top razones de pérdida:\n" +
        "\n".join(f"  {r}: {c} deals" for r, c in sorted(lost_reasons.items(), key=lambda x: -x[1])[:10]) +
        f"\n\nLecciones aprendidas de deals individuales:\n" +
        "\n".join(f"• {l}" for l in all_lessons[:50]) +
        "\n\nGenera 10-15 patrones. Cada patrón:\n"
        '{"pattern_type": "forecast|coaching|risk|opportunity", '
        '"scope": "all|santander|telefonica|tim|telekom", '
        '"pattern": "descripción concreta del patrón con datos", '
        '"confidence": 0.0-1.0, '
        '"sample_size": N}'
    )

    try:
        raw = analyze(system, user, max_tokens=3000)
        text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        text = re.sub(r"\s*```$", "", text)
        patterns = json.loads(text.strip())
    except Exception as e:
        print(f"  Pattern generation failed: {e}")
        return

    supabase.table("learned_patterns").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

    for p in patterns:
        supabase.table("learned_patterns").insert({
            "pattern_type": p.get("pattern_type", "forecast"),
            "scope": p.get("scope", "all"),
            "pattern": p.get("pattern", ""),
            "confidence": p.get("confidence"),
            "sample_size": p.get("sample_size"),
        }).execute()

    print(f"  Generated {len(patterns)} patterns.")
