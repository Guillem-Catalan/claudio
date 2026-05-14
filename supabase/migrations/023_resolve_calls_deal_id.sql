-- ============================================================================
-- 023: Auto-resolve calls.deal_id from hs_deal_id + backfill existing orphans
-- ============================================================================

-- ── Trigger: when a deal is inserted/updated, link orphan calls ───────────

CREATE OR REPLACE FUNCTION resolve_calls_deal_id()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE calls
  SET deal_id = NEW.id
  WHERE hs_deal_id = NEW.deal_id
    AND deal_id IS NULL;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_resolve_calls_deal_id
  AFTER INSERT OR UPDATE OF deal_id ON deals
  FOR EACH ROW
  EXECUTE FUNCTION resolve_calls_deal_id();

-- ── Backfill: fix all existing calls with deal_id NULL ────────────────────

UPDATE calls c
SET deal_id = d.id
FROM deals d
WHERE c.hs_deal_id = d.deal_id
  AND c.deal_id IS NULL
  AND c.hs_deal_id IS NOT NULL;

-- ── Backfill: propagate to audit stubs that inherited NULL deal_ref ───────

UPDATE pae_audits a
SET deal_ref = c.deal_id
FROM calls c
WHERE a.call_ref = c.id
  AND a.deal_ref IS NULL
  AND c.deal_id IS NOT NULL;

UPDATE pbd_audits a
SET deal_ref = c.deal_id
FROM calls c
WHERE a.call_ref = c.id
  AND a.deal_ref IS NULL
  AND c.deal_id IS NOT NULL;
