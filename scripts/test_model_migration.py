"""
Model migration test: run every Claude task with 4 models and compare outputs.
Saves results to model_migration_tests table for analysis.
Does NOT affect production. Does NOT send to real Slack channels.
"""

import json
import os
import re
import sys
import time
import traceback
from datetime import date

from src.db.client import supabase
from src.integrations.claude import analyze

MODELS = [
    "claudio-claude-opus-4-6",
    "claudio-claude-sonnet-4-6",
    "claudio-gpt-5.5",
    "claudio-gpt-5.4-mini",
]

TEST_CHANNEL = "C0ATY3V8CN4"


def _save(deal_id, deal_name, task, model, output=None, output_text=None, error=None, duration_ms=0):
    row = {
        "deal_id": deal_id,
        "deal_name": deal_name,
        "task": task,
        "model": model,
        "duration_ms": duration_ms,
    }
    if output:
        row["output"] = json.dumps(output) if isinstance(output, (dict, list)) else str(output)
    if output_text:
        row["output_text"] = output_text[:10000]
    if error:
        row["error"] = str(error)[:2000]
    supabase.table("model_migration_tests").insert(row).execute()


def _run_with_model(system, user, model, max_tokens=4000):
    start = time.time()
    try:
        raw = analyze(system, user, model=model, max_tokens=max_tokens)
        duration = int((time.time() - start) * 1000)
        return raw, duration, None
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        return None, duration, str(e)


def _get_test_deals(limit=30):
    """Get a diverse mix of deals for testing."""
    deals = []

    # 10 deals with most context (for audit/snapshot)
    r = supabase.table("deals").select(
        "id, deal_id, deal_name, deal_stage, amount, pae, pbd, close_date, deal_context, forecast_category"
    ).not_.is_("deal_context", "null").order("amount", desc=True).limit(10).execute()
    deals.extend(r.data or [])

    # 10 deals in advanced stages
    r = supabase.table("deals").select(
        "id, deal_id, deal_name, deal_stage, amount, pae, pbd, close_date, deal_context, forecast_category"
    ).in_("deal_stage", ["Contract Sent", "Economical Alignment Started", "MEDDPICC Criteria Validation Started"]).not_.is_("deal_context", "null").order("amount", desc=True).limit(10).execute()
    for d in (r.data or []):
        if d["id"] not in {x["id"] for x in deals}:
            deals.append(d)

    # 10 deals in early stages
    r = supabase.table("deals").select(
        "id, deal_id, deal_name, deal_stage, amount, pae, pbd, close_date, deal_context, forecast_category"
    ).in_("deal_stage", ["Factorial Project Alignment started", "Demo Booked"]).not_.is_("deal_context", "null").order("amount", desc=True).limit(10).execute()
    for d in (r.data or []):
        if d["id"] not in {x["id"] for x in deals}:
            deals.append(d)

    return deals[:limit]


# ── Task runners ─────────────────────────────────────────────────────


def test_audit(deal, model):
    """Test audit call scoring."""
    calls = supabase.table("calls").select("*").eq("deal_id", deal["id"]).not_.is_("transcript", "null").order("fecha", desc=True).limit(1).execute()
    if not calls.data:
        return None
    call = calls.data[0]
    transcript = (call.get("transcript") or "")[:30000]
    if len(transcript) < 200:
        return None

    from pathlib import Path
    _ROOT = Path(__file__).resolve().parent.parent
    base = (_ROOT / "src/prompts/base.txt").read_text()
    role_prompt = (_ROOT / "src/prompts/roles/pae.txt").read_text()

    system = base + "\n\n" + role_prompt
    user = f"Deal: {deal['deal_name']}\nStage: {deal['deal_stage']}\n\nTRANSCRIPT:\n{transcript}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=8000)
    _save(deal["id"], deal["deal_name"], "audit", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_snapshot_meddic(deal, model):
    """Test MEDDIC snapshot generation."""
    from pathlib import Path
    _ROOT = Path(__file__).resolve().parent.parent
    base = (_ROOT / "src/prompts/front_deals/base.txt").read_text()
    lang = (_ROOT / "src/prompts/lang_es_startup.txt").read_text()
    output_spec = (_ROOT / "src/prompts/front_deals/output_spec.txt").read_text()

    system = base.replace("{LANG_ES_STARTUP}", lang)
    ctx = (deal.get("deal_context") or "")[:50000]
    user = (
        f"Deal: {deal['deal_name']}\nStage: {deal['deal_stage']}\n"
        f"Amount: {deal.get('amount')}€\nPAE: {deal.get('pae')}\n\n"
        f"DEAL CONTEXT:\n{ctx}\n\n{output_spec}"
    )

    raw, duration, error = _run_with_model(system, user, model, max_tokens=8000)
    parsed = None
    if raw:
        try:
            text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text.strip())
        except:
            parsed = {"raw": raw[:2000]}
    _save(deal["id"], deal["deal_name"], "snapshot_meddic", model, output=parsed, output_text=raw, error=error, duration_ms=duration)
    return parsed


def test_forecast_v1(deal, model):
    """Test forecast v1 (bs/lb classification)."""
    snap = supabase.table("front_deal_snapshots").select("*").eq("deal_id", deal["id"]).order("snapshot_date", desc=True).limit(1).execute()
    if not snap.data:
        return None
    s = snap.data[0]

    from pathlib import Path
    _ROOT = Path(__file__).resolve().parent.parent
    base = (_ROOT / "src/prompts/front_forecast/base.txt").read_text()
    spec = (_ROOT / "src/prompts/front_forecast/output_spec.txt").read_text()

    system = "You are a sales deal classifier. Analyze the current deal snapshot and classify."
    scores = " | ".join(f"{k}={s.get(k.lower(), '?')}" for k in ["M_score", "E_score", "DC_score", "DP_score", "I_score", "C_score"])
    context = f"Deal: {deal['deal_name']}\nStage: {deal['deal_stage']}\nAmount: {deal.get('amount')}€\n{scores}\nSignals: {(s.get('buyer_signals') or '')[:200]}\nBlockers: {(s.get('live_blockers') or '')[:200]}"
    user = f"{base}\n\n{context}\n\n{spec}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=2000)
    parsed = None
    if raw:
        try:
            matches = re.findall(r"\{[^{}]+\}", raw)
            if matches:
                parsed = json.loads(matches[-1])
        except:
            parsed = {"raw": raw[:1000]}
    _save(deal["id"], deal["deal_name"], "forecast_v1", model, output=parsed, output_text=raw, error=error, duration_ms=duration)
    return parsed


def test_forecast_v2(deal, model):
    """Test forecast v2 (benchmark-based)."""
    snap = supabase.table("front_deal_snapshots").select("*").eq("deal_id", deal["id"]).order("snapshot_date", desc=True).limit(1).execute()
    if not snap.data:
        return None

    from src.pipelines.intelligence.forecast_v2 import run as fv2_run
    start = time.time()
    try:
        result = fv2_run(deal["id"], snap.data[0], deal, model=model)
        duration = int((time.time() - start) * 1000)
        _save(deal["id"], deal["deal_name"], "forecast_v2", model, output=result, error=None, duration_ms=duration)
        return result
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        _save(deal["id"], deal["deal_name"], "forecast_v2", model, error=str(e), duration_ms=duration)
        return None


def test_trajectory_lessons(deal, model):
    """Test trajectory lesson extraction."""
    snap_resp = supabase.table("front_deal_snapshots").select(
        "snapshot_date, close_probability, buyer_signals, live_blockers"
    ).eq("deal_id", deal["id"]).order("snapshot_date").limit(10).execute()
    if not snap_resp.data:
        return None

    traj = "\n".join(
        f"  {s['snapshot_date']}: prob={s.get('close_probability','?')}% | signals: {(s.get('buyer_signals') or '')[:60]}"
        for s in snap_resp.data
    )
    ctx = (deal.get("deal_context") or "")[-2000:]

    system = "Eres un analista de Revenue Intelligence. Extrae 3-5 lecciones concretas. Responde SOLO con un JSON array de strings."
    user = f"Deal: {deal['deal_name']} | €{deal.get('amount')} | PAE: {deal.get('pae')}\n\nTrajectory:\n{traj}\n\nContext:\n{ctx}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=1000)
    _save(deal["id"], deal["deal_name"], "trajectory_lessons", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_briefing(deal, model):
    """Test briefing generation."""
    from pathlib import Path
    _ROOT = Path(__file__).resolve().parent.parent
    try:
        prompt_path = _ROOT / "src/prompts/briefing/pae_brief_first_demo_multisector.txt"
        if not prompt_path.exists():
            prompt_path = list((_ROOT / "src/prompts/briefing").glob("*.txt"))[0]
        brief_prompt = prompt_path.read_text()
    except:
        return None

    ctx = (deal.get("deal_context") or "")[-10000:]
    system = brief_prompt[:3000]
    user = f"Deal: {deal['deal_name']}\nStage: {deal['deal_stage']}\nAmount: {deal.get('amount')}€\nPAE: {deal.get('pae')}\n\nCONTEXT:\n{ctx}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=4000)
    _save(deal["id"], deal["deal_name"], "briefing", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_email_draft(deal, model):
    """Test email draft generation."""
    ctx = (deal.get("deal_context") or "")[-5000:]
    if not ctx.strip():
        return None

    system = (
        "Generate a follow-up email in Spanish. Return JSON: "
        '{"recipient": "...", "send_when": "...", "reason": "...", "subject": "...", "body": "..."}'
    )
    user = f"Deal: {deal['deal_name']}\nStage: {deal['deal_stage']}\nAmount: {deal.get('amount')}€\nPAE: {deal.get('pae')}\n\nCONTEXT:\n{ctx}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=2000)
    _save(deal["id"], deal["deal_name"], "email_draft", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_eb_alert(deal, model):
    """Test EB classification + coaching."""
    snap = supabase.table("front_deal_snapshots").select("e_accumulate").eq("deal_id", deal["id"]).order("snapshot_date", desc=True).limit(1).execute()
    if not snap.data or not snap.data[0].get("e_accumulate"):
        return None

    e_acc = snap.data[0]["e_accumulate"]
    system = "Classify the Economic Buyer status. Return JSON: {\"classification\": \"IDENTIFIED_INVOLVED|IDENTIFIED_NOT_INVOLVED|NOT_IDENTIFIED\", \"eb_name\": \"...\", \"eb_role\": \"...\", \"evidence\": \"...\", \"gap\": \"...\"}"
    user = f"Deal: {deal['deal_name']}\n\nE_accumulate:\n{e_acc}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=1000)
    _save(deal["id"], deal["deal_name"], "eb_alert", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_pbd_bant(deal, model):
    """Test PBD BANT snapshot."""
    ctx = (deal.get("deal_context") or "")[-15000:]
    if not ctx.strip():
        return None

    from pathlib import Path
    _ROOT = Path(__file__).resolve().parent.parent
    try:
        prompt = (_ROOT / "src/prompts/pbd_snapshot.txt").read_text()
    except:
        return None

    system = prompt[:3000]
    user = f"Deal: {deal['deal_name']}\nStage: {deal['deal_stage']}\nPBD: {deal.get('pbd')}\n\nCONTEXT:\n{ctx}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=4000)
    _save(deal["id"], deal["deal_name"], "pbd_bant", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_atlas(deal, model):
    """Test atlas company context generation."""
    ctx = (deal.get("deal_context") or "")[:10000]
    system = "Generate company intelligence context in JSON format."
    user = f"Company for deal: {deal['deal_name']}\nContext:\n{ctx[:5000]}"

    raw, duration, error = _run_with_model(system, user, model, max_tokens=3000)
    _save(deal["id"], deal["deal_name"], "atlas", model, output_text=raw, error=error, duration_ms=duration)
    return raw


def test_patterns(model):
    """Test pattern generation (not deal-specific)."""
    traj_resp = supabase.table("deal_trajectories").select("outcome, amount, lessons").limit(50).execute()
    if not traj_resp.data:
        return None

    lessons = []
    for t in traj_resp.data:
        l = t.get("lessons")
        if isinstance(l, str):
            try: l = json.loads(l)
            except: l = []
        lessons.extend(l or [])

    system = "Analiza lecciones de deals cerrados. Genera 5 patterns. Responde con JSON array."
    user = f"Lessons:\n" + "\n".join(f"• {l}" for l in lessons[:30])

    raw, duration, error = _run_with_model(system, user, model, max_tokens=2000)
    _save(None, "AGGREGATE", "patterns", model, output_text=raw, error=error, duration_ms=duration)
    return raw


# ── Main ─────────────────────────────────────────────────────────────


TASK_CONFIG = {
    "audit": {"fn": test_audit, "count": 30},
    "snapshot_meddic": {"fn": test_snapshot_meddic, "count": 30},
    "forecast_v1": {"fn": test_forecast_v1, "count": 20},
    "forecast_v2": {"fn": test_forecast_v2, "count": 20},
    "trajectory_lessons": {"fn": test_trajectory_lessons, "count": 10},
    "briefing": {"fn": test_briefing, "count": 10},
    "email_draft": {"fn": test_email_draft, "count": 10},
    "eb_alert": {"fn": test_eb_alert, "count": 10},
    "pbd_bant": {"fn": test_pbd_bant, "count": 10},
    "atlas": {"fn": test_atlas, "count": 5},
}


def run(task_filter: str | None = None):
    print("=" * 60)
    print("MODEL MIGRATION TEST")
    print(f"Models: {', '.join(MODELS)}")
    print("=" * 60)

    deals = _get_test_deals(30)
    print(f"\n{len(deals)} test deals loaded\n")

    tasks = TASK_CONFIG
    if task_filter:
        tasks = {k: v for k, v in tasks.items() if k == task_filter}

    for task_name, config in tasks.items():
        fn = config["fn"]
        count = config["count"]
        test_deals = deals[:count]

        print(f"\n{'─' * 50}")
        print(f"TASK: {task_name} ({count} deals × {len(MODELS)} models)")
        print(f"{'─' * 50}")

        for i, deal in enumerate(test_deals, 1):
            print(f"\n  [{i}/{count}] {deal['deal_name'][:45]}")
            for model in MODELS:
                model_short = model.split("-", 1)[-1] if "claudio-" in model else model
                try:
                    result = fn(deal, model)
                    status = "OK" if result else "SKIP"
                    print(f"    {model_short:30s} → {status}")
                except Exception as e:
                    print(f"    {model_short:30s} → ERROR: {e}")
                    _save(deal["id"], deal["deal_name"], task_name, model, error=str(e))

    # Pattern test (not deal-specific)
    if not task_filter or task_filter == "patterns":
        print(f"\n{'─' * 50}")
        print(f"TASK: patterns (1 × {len(MODELS)} models)")
        print(f"{'─' * 50}")
        for model in MODELS:
            model_short = model.split("-", 1)[-1] if "claudio-" in model else model
            try:
                test_patterns(model)
                print(f"  {model_short:30s} → OK")
            except Exception as e:
                print(f"  {model_short:30s} → ERROR: {e}")

    print(f"\n{'=' * 60}")
    print("DONE. Check model_migration_tests table for results.")
    print("=" * 60)


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else None
    run(task_filter=task)
