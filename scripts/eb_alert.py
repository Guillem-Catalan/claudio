"""
EB Alert — triggered when a deal enters Pricing and Packaging.

Flow:
1. Load deal from Supabase
2. Load e_accumulate from front_deal_snapshots
3. If missing → build deal_context on-the-fly → generate e_accumulate with Claude
4. Classify EB (haiku) → 3 levels
5. Generate coaching paragraph (sonnet)
6. Post to Slack with exact Block Kit format
"""

import argparse
import os
import time
from datetime import datetime, timezone

from src.db.client import supabase
from src.pipelines.eb_alert.analyze import generate_eb_from_context
from src.pipelines.eb_alert.classifier import classify_eb
from src.pipelines.eb_alert.coaching import generate_coaching
from src.pipelines.eb_alert.slack import SlackClient
from src.pipelines.eb_alert.slack_blocks import (
    PARTNER_CONFIG,
    build_blocks,
    build_missing_frontdeal_blocks,
)
from src.pipelines.sync_deal_context.run import (
    EMAIL_PROPS,
    NOTE_PROPS,
    _build_atlas_header,
    _fetch_associations,
    _batch_read,
    _fetch_owners,
    _format_email,
    _format_note,
    _format_call_context,
    _format_date,
)

SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID") or "C0B1VPPG1F1"


def _build_deal_context(deal_uuid: str, hs_deal_id: str) -> str:
    """Build deal context on-the-fly from atlas + HubSpot + calls/audits."""
    atlas_header = _build_atlas_header(deal_uuid)
    owners = _fetch_owners()

    items: list[tuple[str, str]] = []

    try:
        email_ids = _fetch_associations(hs_deal_id, "emails")
        if email_ids:
            for obj in _batch_read("emails", email_ids, EMAIL_PROPS):
                p = obj.get("properties", {})
                hs_id = str(obj.get("id", ""))
                date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
                items.append((date, _format_email(hs_id, p)))
    except Exception as e:
        print(f"   Email fetch error: {e}")

    try:
        note_ids = _fetch_associations(hs_deal_id, "notes")
        if note_ids:
            for obj in _batch_read("notes", note_ids, NOTE_PROPS):
                p = obj.get("properties", {})
                hs_id = str(obj.get("id", ""))
                date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
                body = p.get("hs_note_body") or ""
                if not body.strip():
                    items.append((
                        date,
                        f"[{_format_date(date)}] NOTE [hs:{hs_id}] — (sin contenido)",
                    ))
                else:
                    items.append((date, _format_note(hs_id, p, owners)))
    except Exception as e:
        print(f"   Note fetch error: {e}")

    calls_result = (
        supabase.table("calls")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("fecha")
        .execute()
    )
    audit_cache: dict[str, dict] = {}
    for table in ("pbd_audits", "pae_audits"):
        for row in (
            supabase.table(table)
            .select("*")
            .eq("deal_ref", deal_uuid)
            .not_.is_("win_rate_score", "null")
            .execute()
        ).data or []:
            audit_cache[row["call_ref"]] = row

    for c in calls_result.data or []:
        c_date = c.get("fecha") or ""
        audit = audit_cache.get(c["id"])
        if audit:
            fecha = (c_date or "?")[:10]
            rol = c.get("rol") or "?"
            tags = c.get("tags") or []
            tags_str = ", ".join(tags) if tags else "untagged"
            dur = round((c.get("duracion_segundos") or 0) / 60)
            rep = c.get("owner_nombre") or c.get("owner_email") or "?"
            call_id = c.get("call_id") or "?"
            wrs = audit.get("win_rate_score")
            ff = audit.get("forecast_flag") or "—"
            entry = (
                f"[{fecha}] CALL AUDITED — {rol} {rep} — Tags: [{tags_str}] ({dur}min) [call:{call_id}]\n"
                f"  Win rate: {wrs} | Forecast: {ff}"
            )
            dc = audit.get("deal_context")
            if dc:
                entry += f"\n  Narrative: {dc[:500]}"
            items.append((c_date, entry))
        else:
            dur_s = c.get("duracion_segundos") or 0
            dur_min = round(dur_s / 60) if dur_s else 0
            owner = c.get("owner_nombre") or c.get("owner_email") or "?"
            hs_id = c.get("hs_call_id") or c["call_id"]
            transcript = c.get("transcript") or ""
            items.append((c_date, _format_call_context(hs_id, {
                "hs_timestamp": c.get("fecha"),
                "hs_call_title": c.get("titulo"),
                "hs_call_body": transcript if len(transcript) >= 200 else "",
            }, owner, dur_min)))

    if not items and not atlas_header:
        return ""

    items.sort(key=lambda x: x[0])
    parts = []
    if atlas_header:
        parts.append(atlas_header)
    parts.append("\n\n".join(text for _, text in items))
    return "\n\n".join(parts)


def _get_or_build_deal_context(deal_uuid: str, hs_deal_id: str) -> str:
    result = (
        supabase.table("deals")
        .select("deal_context")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    ctx = (result.data or {}).get("deal_context") or ""
    if ctx.strip():
        print(f"   Using existing deal_context ({len(ctx)} chars)")
        return ctx

    print("   No deal_context — building on-the-fly ...")
    ctx = _build_deal_context(deal_uuid, hs_deal_id)
    print(f"   Built {len(ctx)} chars")
    return ctx


def _resolve_partner(deal: dict) -> str:
    """Resolve partner name from atlas or deal fields."""
    if deal.get("atlas_id"):
        try:
            atlas_resp = (
                supabase.table("atlas")
                .select("company_name")
                .eq("id", deal["atlas_id"])
                .single()
                .execute()
            )
            if atlas_resp.data:
                return atlas_resp.data["company_name"]
        except Exception:
            pass
    return ""


def _resolve_rep_email(deal_uuid: str, hs_deal_id: str, rol: str) -> str | None:
    """Look up owner_email from calls table for a given role."""
    for col, val in [("deal_id", deal_uuid), ("hs_deal_id", hs_deal_id)]:
        resp = (
            supabase.table("calls")
            .select("owner_email")
            .eq(col, val)
            .eq("rol", rol)
            .not_.is_("owner_email", "null")
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0].get("owner_email")
    return None


def _get_partner_team(email: str | None) -> str:
    """Determine partner team from rep email."""
    if not email:
        return ""
    from src.config import get_subteam
    return get_subteam(email) or ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-uuid", required=True)
    parser.add_argument("--deal-id", required=True)
    args = parser.parse_args()

    print(f"1. Loading deal {args.deal_uuid} ...")
    deal = (
        supabase.table("deals")
        .select("deal_name, amount, pae, pbd, close_date, deal_id, deal_stage, atlas_id, sales_pricing_and_packaging_entered")
        .eq("id", args.deal_uuid)
        .single()
        .execute()
    ).data

    if not deal:
        print(f"   Deal not found: {args.deal_uuid}")
        return

    deal_name = deal["deal_name"]
    hs_deal_id = deal["deal_id"]
    print(f"   Deal: {deal_name}")

    # Resolve PAE/PBD emails from calls table
    ae_email = _resolve_rep_email(args.deal_uuid, hs_deal_id, "PAE")
    pbd_email = _resolve_rep_email(args.deal_uuid, hs_deal_id, "PBD")
    ae_name = deal.get("pae") or ""
    pbd_name = deal.get("pbd") or ""
    print(f"   PAE: {ae_email or ae_name or '—'}, PBD: {pbd_email or pbd_name or '—'}")

    # Resolve partner
    partner_name = _resolve_partner(deal)
    partner_team = _get_partner_team(ae_email) or _get_partner_team(pbd_email)
    print(f"   Partner: {partner_name or '—'}, Team: {partner_team or '—'}")

    ALLOWED_TEAMS = {"Santander", "Telefónica", "Telefonica"}
    if partner_team not in ALLOWED_TEAMS:
        print(f"   Team '{partner_team}' not in allowed list — skipping alert.")
        return

    # Slack client
    slack = SlackClient()

    # Resolve lead Slack IDs
    lead_slack_ids: dict[str, str | None] = {}
    for partner, cfg in PARTNER_CONFIG.items():
        lead_email = cfg.get("lead_email")
        if lead_email:
            lead_slack_ids[partner] = slack.lookup_user_by_email(lead_email)

    # Load e_accumulate from snapshot
    print("2. Loading latest snapshot ...")
    snapshot_resp = (
        supabase.table("front_deal_snapshots")
        .select("e_accumulate, e_score")
        .eq("hs_deal_id", args.deal_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    snapshot = snapshot_resp.data[0] if snapshot_resp.data else None
    e_accumulate = snapshot["e_accumulate"] if snapshot else None
    e_score = snapshot["e_score"] if snapshot else None
    print(f"   EB score: {e_score}, has text: {bool(e_accumulate)}")

    # Fallback: generate e_accumulate inline
    if not e_accumulate:
        print("3. No e_accumulate — generating inline ...")
        deal_context = _get_or_build_deal_context(args.deal_uuid, args.deal_id)
        if deal_context:
            try:
                e_accumulate, e_score = generate_eb_from_context(deal_context, deal)
                print(f"   Generated: score={e_score}")
            except Exception as e:
                print(f"   Claude error: {e}")
                e_accumulate = None
                e_score = None

    # If still no e_accumulate after fallback → missing front_deal alert
    if not e_accumulate:
        print("4. No EB data available — sending missing front_deal alert ...")
        partner_cfg = PARTNER_CONFIG.get(partner_team, {})
        payload = build_missing_frontdeal_blocks(
            deal_id=hs_deal_id,
            deal_name=deal_name,
            partner_name=partner_team,
            lead_slack_user_id=lead_slack_ids.get(partner_team),
            lead_email=partner_cfg.get("lead_email"),
        )
        try:
            ts = slack.post_message(SLACK_CHANNEL_ID, payload)
            print(f"   Sent missing front_deal alert (ts={ts})")
        except Exception as e:
            print(f"   Slack error: {e}")
        return

    # Classify EB
    print("4. Classifying EB ...")
    try:
        result = classify_eb(e_accumulate)
    except Exception as e:
        print(f"   Classifier error: {e}")
        return

    print(f"   Classification: {result.classification}")
    print(f"   EB: {result.eb_name} ({result.eb_role})")

    # Resolve AE Slack mention
    ae_slack_id = None
    if ae_email:
        ae_slack_id = slack.lookup_user_by_email(ae_email)

    # Calculate days in stage
    now_ms = int(time.time() * 1000)
    entered_at = deal.get("sales_pricing_and_packaging_entered") or deal.get("close_date") or ""
    try:
        if entered_at:
            from datetime import datetime as _dt
            entered_dt = _dt.fromisoformat(str(entered_at).replace("Z", "+00:00"))
            days_in_stage = round((time.time() - entered_dt.timestamp()) / 86400, 1)
        else:
            days_in_stage = 0
    except (ValueError, TypeError):
        days_in_stage = 0

    amount_raw = deal.get("amount")
    amount_str = f"€{float(amount_raw):,.0f}" if amount_raw else "N/A"

    # Generate coaching
    print("5. Generating coaching ...")
    try:
        coaching = generate_coaching(
            classification=result.classification,
            deal_name=deal_name,
            amount=amount_str,
            days_in_stage=str(days_in_stage),
            e_accumulate=e_accumulate,
            eb_name=result.eb_name,
            eb_role=result.eb_role,
            evidence=result.evidence,
            gap=result.gap,
        )
        print(f"   Coaching: {coaching[:80]}...")
    except Exception as e:
        print(f"   Coaching error: {e}")
        coaching = f"*EB Status*\n{result.evidence}. {result.gap}"

    # Build Slack payload
    partner_cfg = PARTNER_CONFIG.get(partner_team, {})
    payload = build_blocks(
        classification=result.classification,
        deal_id=hs_deal_id,
        deal_name=deal_name,
        amount=amount_str,
        closedate=str(deal.get("close_date") or ""),
        partner_name=partner_team,
        e_score=e_score,
        eb_name=result.eb_name,
        eb_role=result.eb_role,
        e_accumulate=e_accumulate,
        gap=result.gap,
        coaching=coaching,
        slack_user_id=ae_slack_id,
        ae_email=ae_email,
        ae_name=ae_name,
        lead_slack_user_id=lead_slack_ids.get(partner_team),
        lead_email=partner_cfg.get("lead_email"),
        lead_name=pbd_name,
    )

    # Post to Slack
    print("6. Posting to Slack ...")
    try:
        ts = slack.post_message(SLACK_CHANNEL_ID, payload)
        print(f"   Sent (ts={ts})")
    except Exception as e:
        print(f"   Slack error: {e}")
        return

    print(f"\nDone: {result.classification}")


if __name__ == "__main__":
    main()
