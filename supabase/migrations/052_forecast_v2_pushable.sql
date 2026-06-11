-- ============================================================================
-- Migration 052: Forecast v2 — pushable + push_action + deal_momentum
-- ============================================================================

ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS forecast_pushable BOOLEAN;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS push_action TEXT;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS deal_momentum TEXT;
