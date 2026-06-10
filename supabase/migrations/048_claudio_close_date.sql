-- ============================================================================
-- Migration 048: Add Claudio close date prediction to snapshots
-- ============================================================================
-- Generated inline in the forecast prompt (same Claude call, zero extra cost).
-- claudio_close_date: predicted close date based on stage, velocity, signals, blockers.
-- close_date_reasoning: 1-2 sentence explanation.
-- ============================================================================

ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS claudio_close_date DATE;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS close_date_reasoning TEXT;
