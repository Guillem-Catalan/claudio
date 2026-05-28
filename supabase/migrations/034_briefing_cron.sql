-- ============================================================================
-- Migration 034: Extend daily cron to also create briefings
-- ============================================================================
-- Replaces dispatch_pae_demo_prep() to insert a briefing row per deal with
-- meeting tomorrow. The trg_briefing_dispatch trigger handles dispatch.
-- Meeting type is detected from deal_stage.
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

  FOR deal IN
    SELECT id, id::TEXT AS deal_uuid, deal_name, deal_stage
    FROM deals
    WHERE (
      hs_next_meeting_start_time::date = tomorrow
      OR (hs_next_meeting_start_time IS NULL AND first_meeting_at = tomorrow)
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
    VALUES (deal.id, deal.deal_name, _meeting_type, 'pending');

    RAISE NOTICE 'Dispatched pae_demo_prep + briefing for deal %', deal.deal_uuid;
  END LOOP;
END;
$$ LANGUAGE plpgsql;
