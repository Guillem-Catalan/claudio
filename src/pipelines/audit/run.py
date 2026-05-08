from src.db.client import supabase
from src.integrations.claude import analyze
from src.pipelines.audit.context import get_deal_context
from src.pipelines.audit.prompt_builder import build
from src.pipelines.audit.parser import parse

MAX_PER_CYCLE = 30


def run_single(call_id: str) -> dict | None:
    call = (
        supabase.table("calls")
        .select("*")
        .eq("call_id", call_id)
        .maybe_single()
        .execute()
    )
    if not call.data:
        print(f"  Call {call_id} not found")
        return None

    return _audit(call.data)


def run_pending(limit: int = MAX_PER_CYCLE):
    pbd_audited = {
        r["call_ref"]
        for r in (supabase.table("pbd_audits").select("call_ref").execute()).data
        if r["call_ref"]
    }
    pae_audited = {
        r["call_ref"]
        for r in (supabase.table("pae_audits").select("call_ref").execute()).data
        if r["call_ref"]
    }
    audited_ids = pbd_audited | pae_audited

    all_calls = (
        supabase.table("calls")
        .select("*")
        .order("fecha")
        .execute()
    ).data or []

    pending = [c for c in all_calls if c["id"] not in audited_ids]
    batch = pending[:limit]

    print(f"Found {len(pending)} pending calls, processing {len(batch)}")

    results = []
    for i, call in enumerate(batch, 1):
        print(f"\n[{i}/{len(batch)}] Auditing call {call['call_id']} ({call.get('rol')})...")
        try:
            result = _audit(call)
            if result:
                results.append(result)
        except Exception as e:
            print(f"  [!] Failed: {e}")

    print(f"\nDone: {len(results)}/{len(batch)} audited")
    return results


def _audit(call: dict) -> dict | None:
    role = call.get("rol")
    if not role:
        print(f"  Skipping call {call['call_id']} — no role assigned")
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

    return row
