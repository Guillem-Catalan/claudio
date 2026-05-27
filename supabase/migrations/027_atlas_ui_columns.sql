-- ============================================================================
-- Migration 027: Atlas UI columns (company_card + deal_insights)
-- ============================================================================
-- Structured JSONB for the Atlas modal in the UI dashboard.
-- company_card: ficha visual de la empresa (headline, fit, key_facts, warnings)
-- deal_insights: señales y blockers históricos (buying_signals, blockers, loss_reasons, patterns)
-- ============================================================================

ALTER TABLE atlas ADD COLUMN IF NOT EXISTS company_card JSONB;
ALTER TABLE atlas ADD COLUMN IF NOT EXISTS deal_insights JSONB;
