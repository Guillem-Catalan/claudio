"""
Temporary: create audit stubs for auditable calls that don't have one.
Only creates the stub row (no win_rate_score) — auditing happens separately.
"""

from src.db.client import supabase

BATCH = 1000


def main():
    print("1. Loading existing audit call_refs ...")
    pbd_refs = set()
    offset = 0
    while True:
        r = supabase.table("pbd_audits").select("call_ref").range(offset, offset + BATCH - 1).execute()
        for row in (r.data or []):
            pbd_refs.add(row["call_ref"])
        if len(r.data or []) < BATCH:
            break
        offset += BATCH

    pae_refs = set()
    offset = 0
    while True:
        r = supabase.table("pae_audits").select("call_ref").range(offset, offset + BATCH - 1).execute()
        for row in (r.data or []):
            pae_refs.add(row["call_ref"])
        if len(r.data or []) < BATCH:
            break
        offset += BATCH

    print(f"   PBD entries: {len(pbd_refs)}, PAE entries: {len(pae_refs)}")

    print("2. Finding auditable calls without stub ...")
    pbd_to_create = []
    pae_to_create = []

    offset = 0
    checked = 0
    while True:
        r = (
            supabase.table("calls")
            .select("id, call_id, rol, deal_id, crm_id, hs_deal_id, owner_nombre, transcript")
            .not_.is_("rol", "null")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            break
        for row in rows:
            checked += 1
            t = row.get("transcript") or ""
            if len(t) < 200:
                continue

            rol = row["rol"]
            cid = row["id"]

            if rol == "PBD" and cid not in pbd_refs:
                pbd_to_create.append({
                    "call_ref": cid,
                    "call_id": row["call_id"],
                    "deal_ref": row.get("deal_id"),
                    "crm_id": row.get("crm_id"),
                    "hs_deal_id": row.get("hs_deal_id"),
                    "owner_name": row.get("owner_nombre"),
                })
            elif rol == "PAE" and cid not in pae_refs:
                pae_to_create.append({
                    "call_ref": cid,
                    "call_id": row["call_id"],
                    "deal_ref": row.get("deal_id"),
                    "crm_id": row.get("crm_id"),
                    "hs_deal_id": row.get("hs_deal_id"),
                    "owner_name": row.get("owner_nombre"),
                })
        if len(rows) < BATCH:
            break
        offset += BATCH
        if offset % 5000 == 0:
            print(f"   checked {offset}...")

    print(f"   Checked {checked} calls")
    print(f"   PBD stubs to create: {len(pbd_to_create)}")
    print(f"   PAE stubs to create: {len(pae_to_create)}")

    print("3. Creating stubs ...")
    created = 0
    for i in range(0, len(pbd_to_create), 100):
        batch = pbd_to_create[i : i + 100]
        supabase.table("pbd_audits").upsert(batch, on_conflict="call_ref").execute()
        created += len(batch)
    print(f"   PBD: {created} created")

    created = 0
    for i in range(0, len(pae_to_create), 100):
        batch = pae_to_create[i : i + 100]
        supabase.table("pae_audits").upsert(batch, on_conflict="call_ref").execute()
        created += len(batch)
    print(f"   PAE: {created} created")

    print("Done.")


if __name__ == "__main__":
    main()
