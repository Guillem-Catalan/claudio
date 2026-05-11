-- ============================================================================
-- 006: PAE Demo Prep — daily cron + meeting date columns
-- ============================================================================

-- Add meeting date columns to deals (needed for cron to find demos tomorrow)
ALTER TABLE deals ADD COLUMN IF NOT EXISTS first_meeting_at DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS hs_next_meeting_start_time TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_deals_next_meeting
  ON deals (hs_next_meeting_start_time)
  WHERE hs_next_meeting_start_time IS NOT NULL;

-- ── Function: find deals with demo tomorrow, dispatch workflow ────────────

CREATE OR REPLACE FUNCTION dispatch_pae_demo_prep()
RETURNS void AS $$
DECLARE
  tomorrow DATE := CURRENT_DATE + INTERVAL '1 day';
  deal RECORD;
  github_pat TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  FOR deal IN
    SELECT id::TEXT AS deal_uuid
    FROM deals
    WHERE (
      hs_next_meeting_start_time::date = tomorrow
      OR (hs_next_meeting_start_time IS NULL AND first_meeting_at = tomorrow)
    )
  LOOP
    PERFORM net.http_post(
      url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/pae_demo_prep.yml/dispatches',
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
    RAISE NOTICE 'Dispatched pae_demo_prep for deal %', deal.deal_uuid;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ── pg_cron: daily at 07:00 UTC ──────────────────────────────────────────

SELECT cron.schedule(
  'pae_demo_prep_daily',
  '0 7 * * *',
  'SELECT dispatch_pae_demo_prep()'
);

-- ============================================================================
-- Centralized cron dispatchers: sync_deals + modjo_fetch
-- All scheduling managed from Supabase, GitHub Actions only run on dispatch
-- ============================================================================

-- ── dispatch_sync_deals: daily at 06:00 UTC ─────────────────────────────

CREATE OR REPLACE FUNCTION dispatch_sync_deals()
RETURNS void AS $$
DECLARE
  github_pat TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  PERFORM net.http_post(
    url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/sync_deals.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || github_pat,
      'Accept', 'application/vnd.github.v3+json',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object(
      'ref', 'main',
      'inputs', jsonb_build_object('full', 'false')
    )
  );
END;
$$ LANGUAGE plpgsql;

SELECT cron.schedule(
  'sync_deals_daily',
  '0 6 * * *',
  'SELECT dispatch_sync_deals()'
);

-- ── dispatch_modjo_fetch: every 30 minutes ──────────────────────────────

CREATE OR REPLACE FUNCTION dispatch_modjo_fetch()
RETURNS void AS $$
DECLARE
  github_pat TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  PERFORM net.http_post(
    url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/modjo_fetch.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || github_pat,
      'Accept', 'application/vnd.github.v3+json',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object(
      'ref', 'main'
    )
  );
END;
$$ LANGUAGE plpgsql;

SELECT cron.schedule(
  'modjo_fetch_every_30min',
  '*/30 * * * *',
  'SELECT dispatch_modjo_fetch()'
);
