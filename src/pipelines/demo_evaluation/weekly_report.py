"""Weekly demo coaching report: iterate PAEs, gather data, synthesize, PDF, Slack."""

import json
import re
import unicodedata
from datetime import date, timedelta

from src.config import TEAMS, PAE_CHANNELS, TEAM_LEAD_CHANNELS
from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.demo_evaluation.weekly_prompt import build as build_prompt
from src.pipelines.demo_evaluation.pdf import generate_pdf
from src.pipelines.demo_evaluation.slack import send_demo_report, send_no_demos_notice

def run_weekly(
    pae_email: str | None = None,
    week_start: date | None = None,
    channel_override: str | None = None,
):
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

    print("  Reconciling unrecorded demos ...")
    unrecorded = _reconcile_unrecorded_demos(pae_emails, week_start, week_end)
    if unrecorded:
        print(f"  {len(unrecorded)} unrecorded demos found")

    print("  Finding no-shows ...")
    no_shows = _find_no_shows(pae_emails, week_start, week_end)
    if no_shows:
        print(f"  {len(no_shows)} no-shows found")

    for email in sorted(pae_emails):
        try:
            pae_unrecorded = [d for d in unrecorded if d.get("pae_email") == email]
            pae_no_shows = [d for d in no_shows if d.get("pae_email") == email]
            _process_pae(email, week_start, week_end, channel_override, pae_unrecorded, pae_no_shows)
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


def _process_pae(
    pae_email: str,
    week_start: date,
    week_end: date,
    channel_override: str | None = None,
    unrecorded_demos: list[dict] | None = None,
    no_show_demos: list[dict] | None = None,
):
    print(f"\n  --- {pae_email} ---")

    audit_rows = _get_audit_demos(pae_email, week_start, week_end)

    if not audit_rows:
        demo_calls = _find_demo_calls(pae_email, week_start, week_end)
        if demo_calls:
            print(f"  Found {len(demo_calls)} demo calls without audit_demos — running fallback")
            _run_fallback(demo_calls)
            audit_rows = _get_audit_demos(pae_email, week_start, week_end)

    pae_name = _resolve_pae_name(pae_email)
    team = _get_team(pae_email)
    channel = channel_override or TEAM_LEAD_CHANNELS.get(team, PAE_CHANNELS.get(pae_name) or "C0ATY3V8CN4")
    week_range = f"{week_start.isoformat()} → {(week_end - timedelta(days=1)).isoformat()}"

    if not audit_rows:
        print(f"  No demos — sending notice")
        send_no_demos_notice(pae_name, week_range, channel)
        return

    print(f"  {len(audit_rows)} demos found")

    deals_data = _fetch_deals(audit_rows)
    pbd_names = _resolve_pbd_names(audit_rows, deals_data)

    print(f"  Generating Claude synthesis ...")
    synthesis = _generate_synthesis(pae_name, pae_email, week_start, week_end, audit_rows, deals_data)

    print(f"  Generating PDF ...")
    pdf_bytes = generate_pdf(
        pae_name, week_start, week_end, audit_rows, deals_data, pbd_names, synthesis,
        unrecorded_demos=unrecorded_demos or [],
        no_show_demos=no_show_demos or [],
    )
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
        .contains("tags", '{"Partners - PAE Demo"}')
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
    result = {}
    for r in audit_rows:
        deal_ref = r.get("deal_ref")
        if deal_ref and deal_ref not in result:
            resp = (
                supabase.table("deals")
                .select("*")
                .eq("id", deal_ref)
                .limit(1)
                .execute()
            )
            if resp.data:
                result[deal_ref] = resp.data[0]
                continue

        hs_id = r.get("hs_deal_id")
        if hs_id and not deal_ref:
            resp = (
                supabase.table("deals")
                .select("*")
                .eq("deal_id", hs_id)
                .limit(1)
                .execute()
            )
            if resp.data:
                resolved_ref = resp.data[0]["id"]
                result[resolved_ref] = resp.data[0]
                r["deal_ref"] = resolved_ref
    return result


def _resolve_pbd_names(audit_rows: list[dict], deals_data: dict[str, dict]) -> dict[str, str]:
    deal_refs = {r["deal_ref"] for r in audit_rows if r.get("deal_ref")}
    result = {}
    for ref in deal_refs:
        resp = (
            supabase.table("pbd_audits")
            .select("owner_name")
            .eq("deal_ref", ref)
            .not_.is_("owner_name", "null")
            .limit(1)
            .execute()
        )
        if resp.data:
            result[ref] = resp.data[0]["owner_name"]
            continue

        resp = (
            supabase.table("calls")
            .select("owner_nombre")
            .eq("deal_id", ref)
            .eq("rol", "PBD")
            .not_.is_("owner_nombre", "null")
            .execute()
        )
        if resp.data:
            result[ref] = _most_frequent_name(resp.data, "owner_nombre")
            continue

        hs_deal_id = deals_data.get(ref, {}).get("deal_id")
        if hs_deal_id:
            resp = (
                supabase.table("calls")
                .select("owner_nombre")
                .eq("hs_deal_id", hs_deal_id)
                .eq("rol", "PBD")
                .not_.is_("owner_nombre", "null")
                .execute()
            )
            if resp.data:
                result[ref] = _most_frequent_name(resp.data, "owner_nombre")
    return result


def _most_frequent_name(rows: list[dict], field: str) -> str:
    from collections import Counter
    names = [r[field] for r in rows if r.get(field)]
    if not names:
        return ""
    return Counter(names).most_common(1)[0][0]


def _reconcile_unrecorded_demos(
    pae_emails: set[str],
    week_start: date,
    week_end: date,
) -> list[dict]:
    """Find deals that exited Demo Booked this week but have no audit_demos entry.

    These are demos that happened (deal advanced) but were never recorded in Modjo.
    Returns stub dicts for display in the PDF's unrecorded section.
    """
    resp = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, pae, pbd, amount, "
                "dist_demo_booked_exited, first_meeting_at")
        .gte("dist_demo_booked_exited", week_start.isoformat())
        .lt("dist_demo_booked_exited", week_end.isoformat())
        .execute()
    )
    exited_deals = resp.data or []

    non_demo_stages = {
        "To reschedule", "On Hold", "Demo Booked", "New Deals",
        "Closed Lost", "Opportunity lost",
    }
    candidates = [
        d for d in exited_deals
        if (d.get("deal_stage") or "") not in non_demo_stages
    ]

    existing_refs = set()
    existing_hs = set()
    for email in pae_emails:
        resp = (
            supabase.table("audit_demos")
            .select("deal_ref, hs_deal_id")
            .eq("owner_email", email)
            .gte("demo_date", week_start.isoformat())
            .lt("demo_date", week_end.isoformat())
            .execute()
        )
        for row in (resp.data or []):
            if row.get("deal_ref"):
                existing_refs.add(row["deal_ref"])
            if row.get("hs_deal_id"):
                existing_hs.add(str(row["hs_deal_id"]))

    unrecorded = []
    for d in candidates:
        if d["id"] in existing_refs:
            continue
        if d.get("deal_id") and str(d["deal_id"]) in existing_hs:
            continue

        pae_name = d.get("pae") or ""
        pae_email = _resolve_pae_email(pae_name, pae_emails)

        unrecorded.append({
            "deal_name": d.get("deal_name", "?"),
            "deal_stage": d.get("deal_stage", "?"),
            "amount": d.get("amount"),
            "exit_date": d.get("dist_demo_booked_exited", ""),
            "first_meeting": d.get("first_meeting_at", ""),
            "pae_name": pae_name,
            "pae_email": pae_email,
            "pbd": d.get("pbd", ""),
        })

    return unrecorded


def _find_no_shows(
    pae_emails: set[str],
    week_start: date,
    week_end: date,
) -> list[dict]:
    """Find deals that exited Demo Booked to reschedule/on-hold (no-shows)."""
    resp = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, pae, pbd, amount, "
                "dist_demo_booked_exited, first_meeting_at")
        .gte("dist_demo_booked_exited", week_start.isoformat())
        .lt("dist_demo_booked_exited", week_end.isoformat())
        .execute()
    )
    no_show_stages = {"To reschedule", "On Hold"}
    results = []
    for d in (resp.data or []):
        if (d.get("deal_stage") or "") not in no_show_stages:
            continue
        pae_name = d.get("pae") or ""
        pae_email = _resolve_pae_email(pae_name, pae_emails)
        results.append({
            "deal_name": d.get("deal_name", "?"),
            "deal_stage": d.get("deal_stage", "?"),
            "amount": d.get("amount"),
            "exit_date": d.get("dist_demo_booked_exited", ""),
            "first_meeting": d.get("first_meeting_at", ""),
            "pae_name": pae_name,
            "pae_email": pae_email,
            "pbd": d.get("pbd", ""),
        })
    return results


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _resolve_pae_email(pae_name: str, pae_emails: set[str]) -> str | None:
    if not pae_name:
        return None
    name_parts = _strip_accents(pae_name.lower()).split()
    for email in pae_emails:
        email_low = email.lower()
        if any(len(p) > 2 and p in email_low for p in name_parts):
            return email
    return None


def _generate_synthesis(
    pae_name: str,
    pae_email: str,
    week_start: date,
    week_end: date,
    audit_rows: list[dict],
    deals_data: dict[str, dict],
) -> dict:
    system_prompt, user_prompt = build_prompt(
        pae_name, pae_email, week_start, week_end, audit_rows, deals_data
    )
    response_text = analyze(system_prompt, user_prompt)
    text = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())
