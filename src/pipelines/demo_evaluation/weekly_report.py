"""Weekly demo coaching report: iterate PAEs, gather data, synthesize, PDF, Slack."""

import json
import re
from datetime import date, timedelta

from src.config import TEAMS, PAE_CHANNELS
from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.demo_evaluation.weekly_prompt import build as build_prompt
from src.pipelines.demo_evaluation.pdf import generate_pdf
from src.pipelines.demo_evaluation.slack import send_demo_report, send_no_demos_notice

_BANT_PRIORITY = {"Confirmed": 3, "Partial": 2, "Missing": 1, "N/A": 0}


def run_weekly(pae_email: str | None = None, week_start: date | None = None):
    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)
    week_end = week_start + timedelta(days=7)

    pae_emails: set[str] = set()
    for team_name, team in TEAMS.items():
        if team_name in ("Santander", "Telefónica"):
            pae_emails |= team["pae"]

    if pae_email:
        if pae_email not in pae_emails:
            print(f"  {pae_email} not in Santander/Telefónica PAE list")
            return
        pae_emails = {pae_email}

    print(f"Weekly demo report: {week_start} → {week_end - timedelta(days=1)}")
    print(f"  PAEs to process: {len(pae_emails)}")

    for email in sorted(pae_emails):
        try:
            _process_pae(email, week_start, week_end)
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


def _process_pae(pae_email: str, week_start: date, week_end: date):
    print(f"\n  --- {pae_email} ---")

    audit_rows = _get_audit_demos(pae_email, week_start, week_end)

    if not audit_rows:
        demo_calls = _find_demo_calls(pae_email, week_start, week_end)
        if demo_calls:
            print(f"  Found {len(demo_calls)} demo calls without audit_demos — running fallback")
            _run_fallback(demo_calls)
            audit_rows = _get_audit_demos(pae_email, week_start, week_end)

    pae_name = _resolve_pae_name(pae_email)
    channel = PAE_CHANNELS.get(pae_name) or "C0ATY3V8CN4"
    week_range = f"{week_start.isoformat()} → {(week_end - timedelta(days=1)).isoformat()}"

    if not audit_rows:
        print(f"  No demos — sending notice")
        send_no_demos_notice(pae_name, week_range, channel)
        return

    print(f"  {len(audit_rows)} demos found")

    deals_data = _fetch_deals(audit_rows)
    bant_data = _fetch_bant(audit_rows)

    print(f"  Generating Claude synthesis ...")
    synthesis = _generate_synthesis(pae_name, pae_email, week_start, week_end, audit_rows, deals_data, bant_data)

    print(f"  Generating PDF ...")
    pdf_bytes = generate_pdf(pae_name, week_start, week_end, audit_rows, deals_data, bant_data, synthesis)
    print(f"  PDF: {len(pdf_bytes)} bytes")

    print(f"  Sending to Slack ({channel}) ...")
    mrr_total = sum(float(r.get("amount") or 0) for r in audit_rows)
    mrr_str = f"€{mrr_total:,.0f}" if mrr_total else "—"
    send_demo_report(
        pdf_bytes=pdf_bytes,
        pae_name=pae_name,
        week_range=week_range,
        demo_count=len(audit_rows),
        mrr_total=mrr_str,
        channel=channel,
    )
    print(f"  Done.")


def _get_audit_demos(pae_email: str, week_start: date, week_end: date) -> list[dict]:
    resp = (
        supabase.table("audit_demos")
        .select("*")
        .eq("owner_email", pae_email)
        .gte("demo_date", week_start.isoformat())
        .lt("demo_date", week_end.isoformat())
        .order("demo_date")
        .execute()
    )
    return resp.data or []


def _find_demo_calls(pae_email: str, week_start: date, week_end: date) -> list[dict]:
    resp = (
        supabase.table("calls")
        .select("*")
        .eq("owner_email", pae_email)
        .gte("fecha", week_start.isoformat())
        .lt("fecha", week_end.isoformat())
        .contains("tags", '["Partners - PAE Demo"]')
        .order("fecha")
        .execute()
    )
    return resp.data or []


def _run_fallback(demo_calls: list[dict]):
    from src.pipelines.audit.run import run_single
    from src.pipelines.demo_evaluation.run import run as run_demo_eval
    from src.pipelines.audit.context import get_deal_context

    for call in demo_calls:
        call_id = call["call_id"]
        call_ref = call["id"]

        existing = (
            supabase.table("audit_demos")
            .select("id")
            .eq("call_ref", call_ref)
            .limit(1)
            .execute()
        )
        if existing.data:
            continue

        print(f"    Fallback: auditing call {call_id} ...")
        pae_audit = (
            supabase.table("pae_audits")
            .select("*")
            .eq("call_ref", call_ref)
            .limit(1)
            .execute()
        )
        if not pae_audit.data:
            run_single(call_id)
            pae_audit = (
                supabase.table("pae_audits")
                .select("*")
                .eq("call_ref", call_ref)
                .limit(1)
                .execute()
            )

        existing_demo = (
            supabase.table("audit_demos")
            .select("id")
            .eq("call_ref", call_ref)
            .limit(1)
            .execute()
        )
        if not existing_demo.data:
            deal_context = get_deal_context(
                call.get("deal_id"), call.get("fecha", ""), "PAE"
            )
            run_demo_eval(call, pae_audit.data[0] if pae_audit.data else {}, deal_context)


def _fetch_deals(audit_rows: list[dict]) -> dict[str, dict]:
    deal_refs = {r["deal_ref"] for r in audit_rows if r.get("deal_ref")}
    result = {}
    for ref in deal_refs:
        resp = (
            supabase.table("deals")
            .select("*")
            .eq("id", ref)
            .limit(1)
            .execute()
        )
        if resp.data:
            result[ref] = resp.data[0]
    return result


def _fetch_bant(audit_rows: list[dict]) -> dict[str, dict]:
    deal_refs = {r["deal_ref"] for r in audit_rows if r.get("deal_ref")}
    result = {}
    for ref in deal_refs:
        resp = (
            supabase.table("pbd_audits")
            .select("bant_budget_status, bant_authority_status, bant_need_status, bant_timing_status")
            .eq("deal_ref", ref)
            .not_.is_("bant_budget_status", "null")
            .order("created_at", desc=True)
            .execute()
        )
        if not resp.data:
            continue

        bant = {}
        for pillar, col in [
            ("budget", "bant_budget_status"),
            ("authority", "bant_authority_status"),
            ("need", "bant_need_status"),
            ("timing", "bant_timing_status"),
        ]:
            best = "Missing"
            for row in resp.data:
                status = row.get(col)
                if status and _BANT_PRIORITY.get(status, 0) > _BANT_PRIORITY.get(best, 0):
                    best = status
            bant[pillar] = best
        result[ref] = bant
    return result


def _generate_synthesis(
    pae_name: str,
    pae_email: str,
    week_start: date,
    week_end: date,
    audit_rows: list[dict],
    deals_data: dict[str, dict],
    bant_data: dict[str, dict],
) -> dict:
    system_prompt, user_prompt = build_prompt(
        pae_name, pae_email, week_start, week_end, audit_rows, deals_data, bant_data
    )
    response_text = analyze(system_prompt, user_prompt)
    text = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())
