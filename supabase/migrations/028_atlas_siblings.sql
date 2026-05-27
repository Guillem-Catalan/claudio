-- ============================================================================
-- Migration 028: Atlas sibling CRM IDs
-- ============================================================================
-- Stores all sibling company CRM IDs (same domain in HubSpot) that were
-- aggregated when generating this atlas entry. Enables richer context by
-- merging deals and contacts across duplicate HubSpot companies.
-- ============================================================================

ALTER TABLE atlas ADD COLUMN IF NOT EXISTS sibling_crm_ids TEXT[];
