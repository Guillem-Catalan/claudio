-- ============================================================================
-- Migration 039: Extend briefing cron to cover all meeting sources
-- ============================================================================
-- dispatch_pae_demo_prep() now finds deals with meetings tomorrow from:
--   1. HubSpot fields (hs_next_meeting_start_time, first_meeting_at)
--   2. deal_meetings table (synced from HubSpot engagements)
--   3. calendar_meetings table (synced from Google Calendar, resolved=true)
--
-- Deduplicates by deal UUID so each deal gets at most one briefing + dispatch.
-- ============================================================================

CREATE OR REPLACE FUNCTION dispatch_pae_demo_prep()
RETURNS void AS $$
DECLARE
  tomorrow DATE := CURRENT_DATE + INTERVAL '1 day';
  deal RECORD;
  github_pat TEXT;
  _repo TEXT;
  _meeting_type TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  _repo := current_setting('app.settings.github_repo', true);
  IF _repo IS NULL OR _repo = '' THEN
    _repo := 'Guillem-Catalan/claudio';
  END IF;

  -- Clean up all briefings from previous days
  DELETE FROM briefings WHERE created_at < CURRENT_DATE;

  -- Find ALL deals with meetings tomorrow from any source, deduplicated
  FOR deal IN
    SELECT DISTINCT d.id, d.id::TEXT AS deal_uuid, d.deal_name, d.deal_stage
    FROM deals d
    WHERE d.id IN (
      -- Source 1: HubSpot deal fields
      SELECT id FROM deals
      WHERE hs_next_meeting_start_time::date = tomorrow
         OR (hs_next_meeting_start_time IS NULL AND first_meeting_at = tomorrow)

      UNION

      -- Source 2: deal_meetings table (HubSpot engagements)
      SELECT dm.deal_id FROM deal_meetings dm
      WHERE dm.deal_id IS NOT NULL
        AND dm.meeting_start::date = tomorrow

      UNION

      -- Source 3: calendar_meetings (Google Calendar, resolved only)
      SELECT cm.deal_id FROM calendar_meetings cm
      WHERE cm.deal_id IS NOT NULL
        AND cm.resolved = true
        AND cm.meeting_start::date = tomorrow
    )
  LOOP
    -- 1. Dispatch pae_demo_prep.yml (PDF to Slack)
    PERFORM net.http_post(
      url := 'https://api.github.com/repos/' || _repo || '/actions/workflows/pae_demo_prep.yml/dispatches',
      headers := jsonb_build_object(
        'Authorization', 'Bearer ' || github_pat,
        'Accept', 'application/vnd.github.v3+json',
        'Content-Type', 'application/json'
      ),
      body := jsonb_build_object(
        'ref', 'main',
        'inputs', jsonb_build_object('deal_uuid', deal.deal_uuid)
      )
    );

    -- 2. Create briefing row (trigger handles dispatch)
    _meeting_type := CASE
      WHEN deal.deal_stage IN (
        'Factorial Project Alignment started', 'FPA', 'Demo Booked',
        'Meeting Booked', 'Meeting scheduled', 'Product Alignment', 'Discovery'
      ) THEN 'first_demo'
      WHEN deal.deal_stage = 'MEDDPICC Criteria Validation' THEN 'meddic_review'
      WHEN deal.deal_stage IN ('Economical Allignment', 'Pricing and Packaging') THEN 'pricing'
      WHEN deal.deal_stage = 'Contract Sent' THEN 'closing'
      ELSE 'follow_up'
    END;

    INSERT INTO briefings (deal_id, deal_name, meeting_type, status)
    VALUES (deal.id, deal.deal_name, _meeting_type, 'pending')
    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Dispatched pae_demo_prep + briefing for deal %', deal.deal_uuid;
  END LOOP;
END;
$$ LANGUAGE plpgsql;
