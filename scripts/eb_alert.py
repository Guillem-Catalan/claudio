"""Send EB alert when a deal enters Pricing and Packaging."""

import argparse

from src.db.client import supabase
from src.pipelines.eb_alert.analyze import generate_eb_assessment
from src.pipelines.eb_alert.slack import send_eb_alert
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
    """Read deal_context from DB; if empty, build on-the-fly."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-uuid", required=True)
    parser.add_argument("--deal-id", required=True)
    args = parser.parse_args()

    print(f"1. Loading deal {args.deal_uuid} ...")
    deal = (
        supabase.table("deals")
        .select("deal_name, amount, pae, pbd, close_date, deal_id, deal_stage, atlas_id")
        .eq("id", args.deal_uuid)
        .single()
        .execute()
    ).data

    if not deal:
        print(f"   Deal not found: {args.deal_uuid}")
        return

    print(f"   Deal: {deal['deal_name']}")

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
    eb_text = snapshot["e_accumulate"] if snapshot else None
    eb_score = snapshot["e_score"] if snapshot else None
    print(f"   EB score: {eb_score}, has text: {bool(eb_text)}")

    if not eb_text:
        print("3. No EB data in snapshot — generating inline ...")
        deal_context = _get_or_build_deal_context(args.deal_uuid, args.deal_id)
        if deal_context:
            try:
                eb_text, eb_score = generate_eb_assessment(deal_context, deal)
                print(f"   Generated: score={eb_score}, text={eb_text[:80]}...")
            except Exception as e:
                print(f"   Claude error: {e}")
                eb_text = "Error generating EB assessment"
                eb_score = None
        else:
            eb_text = "No deal context available — no calls, emails, or notes found for this deal."

    partner = None
    if deal.get("atlas_id"):
        print("4. Resolving partner ...")
        atlas_resp = (
            supabase.table("atlas")
            .select("company_name")
            .eq("id", deal["atlas_id"])
            .single()
            .execute()
        )
        if atlas_resp.data:
            partner = atlas_resp.data["company_name"]
            print(f"   Partner: {partner}")

    print("5. Sending Slack alert ...")
    ok = send_eb_alert(
        deal_name=deal["deal_name"],
        deal_id=deal["deal_id"],
        pae=deal.get("pae"),
        pbd=deal.get("pbd"),
        amount=deal.get("amount"),
        close_date=str(deal["close_date"]) if deal.get("close_date") else None,
        partner=partner,
        eb_status_text=eb_text,
        eb_score=eb_score,
    )
    print(f"\nDone: {'sent' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
