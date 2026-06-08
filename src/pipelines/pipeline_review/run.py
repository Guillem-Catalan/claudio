"""Weekly TL pipeline review: iterate PAEs, gather deals + snapshots, synthesize, PDF, Slack."""

import json
import re

from src.config import TEAMS, TEAM_LEAD_CHANNELS
from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.pipeline_review.prompt import build as build_prompt
from src.pipelines.pipeline_review.pdf import generate_pdf
from src.pipelines.demo_evaluation.slack import send_demo_report

ADVANCED_STAGES = {
    "Factorial Project Alignment started",
    "Product Alignment",
    "MEDDPICC Criteria Validation Started",
    "Economical Allignment Started", "Economical Alignment Started",
    "Pricing and Packaging",
    "Pricing & Packaging",
    "Contract Sent",
}

MIN_PROBABILITY = 46


def run_all(
    pae_email: str | None = None,
    channel_override: str | None = None,
):
    pae_emails: set[str] = set()
    for team_name, team in TEAMS.items():
        if team.get("active") and not team.get("backfill_only"):
            pae_emails |= team["pae"]

    if pae_email:
        if pae_email not in pae_emails:
            print(f"  {pae_email} not in active PAE list")
            return
        pae_emails = {pae_email}

    print(f"TL Pipeline Review")
    print(f"  PAEs to process: {len(pae_emails)}")

    for email in sorted(pae_emails):
        try:
            _process_pae(email, channel_override)
        except Exception as e:
            print(f"  ERROR processing {email}: {e}")


def _resolve_pae_name(email: str) -> str:
    resp = (
        supabase.table("calls")
        .select("owner_nombre")
        .eq("owner_email", email)
        .not_.is_("owner_nombre", "null")
        .limit(1)
        .execute()
    )
    if resp.data:
        return resp.data[0]["owner_nombre"]
    return email.split("@")[0].replace(".", " ").title()


def _get_team(pae_email: str) -> str | None:
    for team_name, team in TEAMS.items():
        if pae_email in team.get("pae", set()):
            return team_name
    return None


def _fetch_advanced_deals(pae_name: str) -> list[dict]:
    first_last = pae_name.split()[:2]
    pattern = f"%{'%'.join(first_last)}%" if len(first_last) >= 2 else f"%{pae_name}%"
    resp = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, amount, deal_age_days, pbd, pae")
        .ilike("pae", pattern)
        .order("amount", desc=True)
        .execute()
    )
    return [d for d in (resp.data or []) if d.get("deal_stage") in ADVANCED_STAGES]


def _fetch_latest_snapshots(deal_ids: list[str]) -> dict[str, dict]:
    if not deal_ids:
        return {}
    all_snaps = []
    for i in range(0, len(deal_ids), 30):
        batch = deal_ids[i:i + 30]
        resp = (
            supabase.table("front_deal_snapshots")
            .select(
                "deal_id, snapshot_date, close_probability, "
                "m_score, e_score, dc_score, dp_score, i_score, c_score, "
                "deal_summary, live_blockers, buyer_signals, objections, "
                "next_step, deal_strengths, improvements"
            )
            .in_("deal_id", batch)
            .order("snapshot_date", desc=True)
            .limit(len(batch) * 3)
            .execute()
        )
        all_snaps.extend(resp.data or [])

    latest: dict[str, dict] = {}
    for s in all_snaps:
        did = s["deal_id"]
        if did not in latest:
            latest[did] = s
    return latest


def _process_pae(pae_email: str, channel_override: str | None = None):
    print(f"\n  --- {pae_email} ---")

    pae_name = _resolve_pae_name(pae_email)
    team = _get_team(pae_email)
    channel = channel_override or TEAM_LEAD_CHANNELS.get(team, "C0ATY3V8CN4")

    deals = _fetch_advanced_deals(pae_name)
    if not deals:
        print(f"  No advanced deals for {pae_name}")
        return

    deal_ids = [d["id"] for d in deals]
    snapshots = _fetch_latest_snapshots(deal_ids)

    qualified = []
    for d in deals:
        snap = snapshots.get(d["id"])
        if snap and (snap.get("close_probability") or 0) >= MIN_PROBABILITY:
            qualified.append({"deal": d, "snap": snap})

    if not qualified:
        print(f"  {len(deals)} advanced deals but none with prob >= {MIN_PROBABILITY}%")
        return

    print(f"  {len(qualified)} deals qualified (of {len(deals)} advanced)")

    print(f"  Generating Claude synthesis ...")
    synthesis = _generate_synthesis(pae_name, qualified)

    print(f"  Generating PDF ...")
    try:
        pdf_bytes = generate_pdf(pae_name, qualified, synthesis)
        print(f"  PDF: {len(pdf_bytes)} bytes")
    except Exception as e:
        if "gobject" in str(e).lower() or "pango" in str(e).lower():
            print(f"  WeasyPrint not available locally — writing HTML preview instead")
            from src.pipelines.pipeline_review.pdf import generate_html
            html = generate_html(pae_name, qualified, synthesis)
            path = f"/tmp/pipeline-review-{pae_name.lower().replace(' ', '-')}.html"
            with open(path, "w") as f:
                f.write(html)
            print(f"  HTML preview: {path}")
            return
        raise

    mrr_total = sum(float(q["deal"].get("amount") or 0) for q in qualified)
    mrr_str = f"€{mrr_total:,.0f}" if mrr_total else "—"

    print(f"  Sending to Slack ({channel}) ...")
    send_demo_report(
        pdf_bytes=pdf_bytes,
        pae_name=pae_name,
        week_range="Pipeline Review",
        demo_count=len(qualified),
        mrr_total=mrr_str,
        channel=channel,
    )
    print(f"  Done.")


def _generate_synthesis(pae_name: str, qualified: list[dict]) -> dict:
    system_prompt, user_prompt = build_prompt(pae_name, qualified)
    response_text = analyze(system_prompt, user_prompt)
    text = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())
