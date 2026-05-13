"""
Compute close_probability and claudio_forecast for a front_deal snapshot.
Reads the snapshot, calls Claude to classify deal-killer/bs/lb,
applies the weighted formula, and updates the row.
"""

import json
import re
from pathlib import Path

from src.db.client import supabase
from src.integrations.claude import analyze

_ROOT = Path(__file__).resolve().parent.parent.parent
_BASE = (_ROOT / "prompts/front_forecast/base.txt").read_text()
_OUTPUT_SPEC = (_ROOT / "prompts/front_forecast/output_spec.txt").read_text()

_SYSTEM = (
    "You are a sales deal classifier. "
    "Analyze the current deal snapshot and classify: deal-killer presence, "
    "buyer signal strength (bs), and blocker severity (lb). "
    "Do not compute any formula — Python handles the math. "
    "End your response with the JSON object on the last line, with no text after it. "
    '{"deal_killer": <bool>, "deal_killer_value": <int 0-7 or null>, "bs": <float>, "lb": <float>}'
)


def _build_context(snap: dict, close_date: str) -> str:
    scores = " | ".join(
        f"{k}={snap.get(k.lower(), '?')}"
        for k in ["M_score", "E_score", "DC_score", "DP_score", "I_score", "C_score"]
    )
    lines = [
        "=== CONTEXTO DEL DEAL ===",
        "",
        f"Deal_Name: {snap.get('deal_name') or '?'}",
        f"Stage: {snap.get('stage') or '?'}",
        f"deal_age: {snap.get('deal_age') or '?'} días",
        f"Close_date esperada: {close_date}",
        f"MRR: {snap.get('mrr') or '?'}€",
        f"HS_forecast_category: {snap.get('hs_forecast_category') or '?'}",
        "",
        "=== SNAPSHOT ACTUAL ===",
        "",
        scores,
        f"buyer_signals: {snap.get('buyer_signals') or 'Ninguna'}",
        f"live_blockers: {snap.get('live_blockers') or 'Ninguno'}",
        f"Deal_Summary: {snap.get('deal_summary') or '-'}",
        f"next_step: {snap.get('next_step') or '-'}",
        f"objections: {snap.get('objections') or 'Ninguna'}",
    ]
    return "\n".join(lines)


def _parse_response(raw: str) -> dict:
    matches = re.findall(r"\{[^{}]+\}", raw)
    if not matches:
        raise ValueError(f"no JSON found in response")
    return json.loads(matches[-1])


def _compute_probability(snap: dict, claude_out: dict) -> int:
    if claude_out.get("deal_killer"):
        val = claude_out.get("deal_killer_value")
        return int(val) if val is not None else 3

    try:
        C = float(snap.get("c_score", 0) or 0)
        E = float(snap.get("e_score", 0) or 0)
        DP = float(snap.get("dp_score", 0) or 0)
        DC = float(snap.get("dc_score", 0) or 0)
        I = float(snap.get("i_score", 0) or 0)
        M = float(snap.get("m_score", 0) or 0)
    except (TypeError, ValueError):
        return 0

    bs = float(claude_out.get("bs") or 0)
    lb = float(claude_out.get("lb") or 0)

    base = C * 0.15 + E * 0.25 + DP * 0.20 + DC * 0.20 + I * 0.15 + M * 0.05
    adjusted = max(0.0, min(10.0, base + bs + lb))
    return round(adjusted * 10)


def run(snapshot_id: str):
    print(f"1. Loading snapshot {snapshot_id} ...")
    snap = (
        supabase.table("front_deal_snapshots")
        .select("*")
        .eq("id", snapshot_id)
        .maybe_single()
        .execute()
    )
    if not snap.data:
        print(f"   Snapshot not found — skipping")
        return

    snap = snap.data

    if snap.get("close_probability") is not None:
        print(f"   Already has close_probability={snap['close_probability']} — skipping")
        return

    deal_name = snap.get("deal_name") or "?"
    print(f"   Deal: {deal_name}")

    close_date = "?"
    if snap.get("deal_id"):
        deal = (
            supabase.table("deals")
            .select("close_date")
            .eq("id", snap["deal_id"])
            .maybe_single()
            .execute()
        )
        if deal.data:
            close_date = deal.data.get("close_date") or "?"

    print("2. Calling Claude ...")
    context = _build_context(snap, close_date)
    prompt = f"{_BASE}\n\n{context}\n\n{_OUTPUT_SPEC}"
    raw = analyze(_SYSTEM, prompt, max_tokens=2000)

    print("3. Parsing response ...")
    claude_out = _parse_response(raw)
    close_probability = _compute_probability(snap, claude_out)
    print(
        f"   deal_killer={claude_out.get('deal_killer')} "
        f"bs={claude_out.get('bs')} lb={claude_out.get('lb')} "
        f"→ {close_probability}%"
    )

    mrr = float(snap.get("mrr") or 0)
    claudio_forecast = round((close_probability / 100) * mrr, 2)
    print(f"   forecast={claudio_forecast}€")

    print("4. Updating snapshot ...")
    supabase.table("front_deal_snapshots").update({
        "close_probability": close_probability,
        "claudio_forecast": claudio_forecast,
    }).eq("id", snapshot_id).execute()

    print(f"   Done: {deal_name} → {close_probability}% / {claudio_forecast}€")
