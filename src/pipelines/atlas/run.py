"""
Atlas: generate company historical context for audit enrichment.

Steps:
    1. Fetch company info from HubSpot (name, industry, etc.)
    2. Read all deals for this company from Supabase
    3. Build structured deal history
    4. Call Claude to synthesize company context
    5. Write output to atlas table + set last_generated
"""

from src.db.client import supabase


def generate(atlas_id: str, crm_id: str):
    print(f"1. Loading atlas stub {atlas_id} (crm_id={crm_id}) ...")

    # TODO: implement when output columns are defined
    raise NotImplementedError("Atlas pipeline not yet implemented — output columns TBD")
