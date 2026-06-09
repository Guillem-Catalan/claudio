-- ============================================================================
-- Migration 047: Add Competition pillar to MEDDICC
-- ============================================================================
-- MEDDIC → MEDDICC: second C = Competition.
-- Already tracked in pae_audits (meddic_competition_status/evidence).
-- Now elevated to front_deal_snapshots for forecasting and UI display.
-- ============================================================================

ALTER TABLE front_deal_snapshots
    ADD COLUMN IF NOT EXISTS comp_accumulate TEXT,
    ADD COLUMN IF NOT EXISTS comp_score NUMERIC;
