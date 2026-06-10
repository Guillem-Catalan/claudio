-- ============================================================================
-- Migration 050: Save pipeline_name + owner fallback from calls
-- ============================================================================
-- 1. pipeline_name column on deals — populated by sync_deals
-- 2. Views updated to filter by pipeline (Partners Distribution + Sales Pipeline + any with PAE)
-- 3. sync_deals fallback: if no PAE/PBD from HubSpot owner, check calls table
-- ============================================================================

ALTER TABLE deals ADD COLUMN IF NOT EXISTS pipeline_name TEXT;
