-- ============================================================================
-- Migration 053: Delete briefings when new snapshot is generated (post-meeting)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_briefing_after_snapshot()
RETURNS TRIGGER AS $$
BEGIN
  DELETE FROM briefings WHERE deal_id = NEW.deal_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cleanup_briefing_after_snapshot
  AFTER INSERT ON front_deal_snapshots
  FOR EACH ROW
  EXECUTE FUNCTION cleanup_briefing_after_snapshot();
