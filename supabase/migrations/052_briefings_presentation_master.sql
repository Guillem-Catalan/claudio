-- ============================================================================
-- Migration 052: Briefings via Presentation Master
-- ============================================================================
-- Add share_url, use_case_key, presentation_url to briefings table.
-- Disable old cron-based briefing generation.
-- ============================================================================

ALTER TABLE briefings ADD COLUMN IF NOT EXISTS share_url TEXT;
ALTER TABLE briefings ADD COLUMN IF NOT EXISTS use_case_key TEXT;
ALTER TABLE briefings ADD COLUMN IF NOT EXISTS presentation_url TEXT;

-- Disable old cron (dispatch_pae_demo_prep)
SELECT cron.unschedule('pae_demo_prep_daily');
