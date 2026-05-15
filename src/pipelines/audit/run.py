from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.audit.context import get_deal_context, append_audit_to_context
from src.pipelines.audit.prompt_builder import build
from src.pipelines.audit.parser import parse


def run_single(call_id: str) -> dict | None:
    resp = (
        supabase.table("calls")
        .select("*")
        .eq("call_id", call_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        print(f"  Call {call_id} not found")
        return None

    call = resp.data[0]
    if _already_audited(call):
        print(f"  Skipping call {call_id} — already audited")
        return None

    return _audit(call)


def _already_audited(call: dict) -> bool:
    role = call.get("rol")
    if not role:
        return False
    table = "pbd_audits" if role == "PBD" else "pae_audits"
    resp = (
        supabase.table(table)
        .select("win_rate_score")
        .eq("call_ref", call["id"])
        .limit(1)
        .execute()
    )
    if not resp.data:
        return False
    return resp.data[0].get("win_rate_score") is not None


def _audit(call: dict) -> dict | None:
    role = call.get("rol")
    if not role:
        print(f"  Skipping call {call['call_id']} — no role assigned")
        return None

    if call.get("deal_id"):
        deal_resp = (
            supabase.table("deals")
            .select("deal_name")
            .eq("id", call["deal_id"])
            .limit(1)
            .execute()
        )
        if deal_resp.data and "session" in (deal_resp.data[0].get("deal_name") or "").lower():
            print(f"  Skipping call {call['call_id']} — onboarding deal")
            return None

    deal_context = get_deal_context(
        deal_uuid=call.get("deal_id"),
        call_date=call.get("fecha", ""),
        role=role,
    )

    system_prompt, user_prompt = build(call, deal_context)

    print(f"  Sending to Claude ({role})...")
    response_text = analyze(system_prompt, user_prompt)

    print(f"  Parsing response...")
    fields = parse(response_text, role)

    table = "pbd_audits" if role == "PBD" else "pae_audits"
    row = {
        "call_ref": call["id"],
        "call_id": call["call_id"],
        "deal_ref": call.get("deal_id"),
        "crm_id": call.get("crm_id"),
        "hs_deal_id": call.get("hs_deal_id"),
        "owner_name": call.get("owner_nombre"),
        **fields,
    }

    supabase.table(table).upsert(row, on_conflict="call_ref").execute()
    print(f"  Written to {table}")

    if call.get("deal_id"):
        print(f"  Appending audit result to deal_context ...")
        append_audit_to_context(call["deal_id"], call, fields)

    if role == "PAE" and _is_demo_call(call):
        from src.config import get_subteam
        team = get_subteam(call.get("owner_email") or "")
        if team in ("Santander", "Telefónica"):
            try:
                from src.pipelines.demo_evaluation.run import run as run_demo_eval
                print(f"  Demo detected ({team}) — running demo evaluation ...")
                run_demo_eval(call, row, deal_context)
            except Exception as e:
                print(f"  Demo evaluation error: {e}")
        else:
            print(f"  Demo detected but team '{team or '?'}' not enabled — skipping demo eval")

    return row


def _is_demo_call(call: dict) -> bool:
    tags = call.get("tags") or []
    return "Partners - PAE Demo" in tags
