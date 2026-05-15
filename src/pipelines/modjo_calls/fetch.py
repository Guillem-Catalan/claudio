from datetime import datetime, timedelta, timezone

from src.config import (
    ALL_PARTNER_NAMES,
    ALL_PBD_EMAILS,
    ALL_PAE_EMAILS,
    ALL_REP_EMAILS,
    ALL_TARGET_EMAILS,
    PBD_TAGS,
    PAE_TAGS,
    get_role,
    get_subteam,
)
from src.pipelines.modjo_calls.api_client import (
    fetch_user_ids,
    scan_call_ids,
    fetch_call_details,
)
from src.db.client import supabase

MIN_TRANSCRIPT_LENGTH = 100


def _build_transcript(lines: list[dict]) -> str:
    parts = []
    for t in lines:
        try:
            start = t.get("startTime") or 0
            content = t.get("content", "")
            parts.append(f"[{int(start // 60):02d}:{int(start) % 60:02d}] {content}")
        except Exception:
            continue
    return "\n".join(parts)


def _count_speakers(lines: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in lines:
        speaker = line.get("userName") or line.get("speaker", "")
        if speaker:
            counts[speaker] = counts.get(speaker, 0) + 1
    return counts


def _resolve_owner(
    users: list[dict], tags: list[str], speaker_counts: dict[str, int]
) -> tuple[dict, str | None] | tuple[None, None]:
    reps = [u for u in users if u.get("email", "") in ALL_REP_EMAILS]

    if reps:
        has_pae_tag = any(t in PAE_TAGS for t in tags)
        has_pbd_tag = any(t in PBD_TAGS for t in tags)

        if has_pae_tag:
            pae_rep = next((u for u in reps if u["email"] in ALL_PAE_EMAILS), None)
            if pae_rep:
                return pae_rep, "PAE"

        owner = next((u for u in reps if u.get("isOwner")), None)
        if owner is None:
            owner = max(reps, key=lambda u: speaker_counts.get(u.get("name", ""), 0))

        role = get_role(owner["email"], tags)
        if role is None:
            if has_pbd_tag:
                role = "PBD"
            elif has_pae_tag:
                role = "PAE"
            else:
                role = "PBD"
        return owner, role

    targets = [u for u in users if u.get("email", "") in ALL_TARGET_EMAILS]
    if targets:
        owner = next((u for u in targets if u.get("isOwner")), targets[0])
        return owner, None

    return None, None


def normalize(raw: dict) -> dict | None:
    rels = raw.get("relations") or {}
    users = rels.get("users", [])
    transcript_lines = rels.get("transcript", [])

    tags = [t["name"] for t in rels.get("tags", [])]

    transcript = _build_transcript(transcript_lines)
    if len(transcript.strip()) < MIN_TRANSCRIPT_LENGTH:
        return None

    speaker_counts = _count_speakers(transcript_lines)
    owner, role = _resolve_owner(users, tags, speaker_counts)
    if owner is None:
        return None

    owner_email = owner.get("email", "")

    account = rels.get("account") or {}
    if isinstance(account, list):
        account = account[0] if account else {}

    account_name = account.get("name", "")
    is_partner = account_name.lower().strip() in ALL_PARTNER_NAMES

    crm_id = ""
    if account_name and not is_partner:
        crm_id = str(account.get("accountCrmId") or account.get("accountId") or "")

    deal = rels.get("deal") or {}
    hs_deal_id = str(deal.get("dealCrmId") or "")

    return {
        "call_id": str(raw["callId"]),
        "titulo": raw.get("title", ""),
        "fecha": raw.get("startDate"),
        "duracion_segundos": int(raw.get("duration", 0)),
        "owner_email": owner_email,
        "owner_nombre": owner.get("name", ""),
        "rol": role,
        "tags": tags,
        "team": "Partners",
        "crm_id": crm_id,
        "hs_deal_id": hs_deal_id,
        "transcript": transcript,
        "subteam": get_subteam(owner_email),
    }


def _resolve_deal_uuid(hs_deal_id: str) -> str | None:
    if not hs_deal_id:
        return None
    try:
        result = (
            supabase.table("deals")
            .select("id")
            .eq("deal_id", hs_deal_id)
            .maybe_single()
            .execute()
        )
        return result.data["id"] if result.data else None
    except Exception:
        return None


def _upsert_calls(calls: list[dict]) -> int:
    rows = []
    for call in calls:
        deal_uuid = _resolve_deal_uuid(call["hs_deal_id"])
        rows.append({
            "call_id": call["call_id"],
            "deal_id": deal_uuid,
            "crm_id": call["crm_id"] or None,
            "hs_deal_id": call["hs_deal_id"] or None,
            "titulo": call["titulo"],
            "fecha": call["fecha"],
            "owner_email": call["owner_email"],
            "owner_nombre": call["owner_nombre"],
            "rol": call["rol"],
            "tags": call["tags"],
            "team": call["team"],
            "duracion_segundos": call["duracion_segundos"],
            "transcript": call["transcript"],
            "subteam": call["subteam"],
            "source": "modjo",
        })

    if not rows:
        return 0

    result = (
        supabase.table("calls")
        .upsert(rows, on_conflict="call_id")
        .execute()
    )
    return len(result.data)


def run(since: datetime | None = None):
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=2)

    print("1. Resolving Modjo user IDs...")
    id_to_email = fetch_user_ids(ALL_TARGET_EMAILS)
    print(f"   {len(id_to_email)} users found")

    print("\n2. Scanning for calls...")
    call_ids = scan_call_ids(set(id_to_email.keys()), since)
    print(f"   {len(call_ids)} calls found")

    if not call_ids:
        print("\n   No new calls.")
        return []

    print("\n3. Fetching transcripts...")
    raw_calls = fetch_call_details(call_ids)

    print("\n4. Normalizing...")
    calls = [c for raw in raw_calls if (c := normalize(raw)) is not None]
    print(f"   {len(calls)} calls with valid transcripts")

    print("\n5. Writing to Supabase...")
    written = _upsert_calls(calls)
    print(f"   {written} calls upserted")

    print("\n6. Auditing calls...")
    from src.pipelines.audit.run import run_single

    audited = 0
    for call in calls:
        if not call["rol"]:
            continue
        try:
            result = run_single(call["call_id"])
            if result:
                audited += 1
                print(f"   {call['call_id']}: win_rate={result.get('win_rate_score')}")
        except Exception as e:
            print(f"   {call['call_id']}: ERROR {e}")
    print(f"   {audited} calls audited")

    return calls
