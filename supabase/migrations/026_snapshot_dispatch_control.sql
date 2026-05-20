-- ============================================================================
-- Migration 026: Snapshot dispatch control
-- ============================================================================
--
-- Problem: dc_on_snapshot_ready dispatches front_deals.yml immediately per deal.
-- When sync_deals updates hundreds of deals, this creates a thundering herd of
-- GitHub Actions runs that overwhelm Azure Claude rate limits. Failed dispatches
-- leave front_deal_triggered_at set with no retry mechanism. Also, atlas_ready
-- blocked deals without atlas_id from ever getting snapshots.
--
-- Fix: 4-layer approach
--   1. Remove HTTP dispatch from dc_on_snapshot_ready (becomes no-op)
--   2. New pg_cron dispatch_pending_snapshots() — batched, atlas_ready not required
--   3. New pg_cron retry_stale_snapshots() — auto-recovery for failed dispatches
--   4. New pg_cron retry_stale_context_syncs() — re-dispatch stuck context syncs
-- ============================================================================


-- ── 1. Simplify dc_on_snapshot_ready ───────────────────────────────────────
-- Dispatch is now handled by pg_cron batch. Trigger only guards session deals.

CREATE OR REPLACE FUNCTION dc_on_snapshot_ready()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT (NEW.calls_ready AND NEW.emails_ready AND NEW.notes_ready AND NEW.atlas_ready) THEN
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── 2. Batch dispatch: up to 10 pending snapshots per invocation ───────────

CREATE OR REPLACE FUNCTION dispatch_pending_snapshots()
RETURNS INTEGER AS $$
DECLARE
    _pat   TEXT;
    _rec   RECORD;
    _count INTEGER := 0;
    _active_stages TEXT[] := ARRAY[
        'Factorial Project Alignment started',
        'Demo Booked', 'Meeting Booked',
        'MEDDPICC Criteria Validation Started',
        'Economical Allignment Started',
        'Pricing and Packaging', 'Pricing & Packaging',
        'Contract Sent',
        'Discovery', 'Product Alignment',
        'Pre-qualified', 'Engaged', 'Attempting to contact',
        'Associating the partner', 'Research & Outreach',
        'New', 'New Deals', 'Opportunity detected',
        'On Hold', 'Nurturing', 'To reschedule',
        'Sales Nurturing', 'Connected - Not Engaged'
    ];
BEGIN
    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat'
    LIMIT 1;

    IF _pat IS NULL THEN
        RAISE WARNING 'github_pat not found in vault';
        RETURN 0;
    END IF;

    FOR _rec IN
        SELECT dc.id, dc.deal_id, dc.hs_deal_id
        FROM deal_confirmations dc
        JOIN deals d ON d.id = dc.deal_id
        WHERE dc.calls_ready
          AND dc.emails_ready
          AND dc.notes_ready
          AND dc.front_deal_triggered_at IS NULL
          AND d.deal_stage = ANY(_active_stages)
          AND LOWER(d.deal_name) NOT LIKE '%session%'
          AND d.deal_context IS NOT NULL
          AND LENGTH(d.deal_context) > 0
        ORDER BY dc.updated_at ASC
        LIMIT 10
    LOOP
        PERFORM net.http_post(
            url     := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/front_deals.yml/dispatches',
            headers := jsonb_build_object(
                'Authorization', 'Bearer ' || _pat,
                'Accept', 'application/vnd.github.v3+json',
                'Content-Type', 'application/json'
            ),
            body    := jsonb_build_object(
                'ref', 'main',
                'inputs', jsonb_build_object(
                    'deal_uuid', _rec.deal_id::text,
                    'hs_deal_id', _rec.hs_deal_id
                )
            )
        );

        UPDATE deal_confirmations
        SET front_deal_triggered_at = now()
        WHERE id = _rec.id;

        _count := _count + 1;
    END LOOP;

    RETURN _count;
END;
$$ LANGUAGE plpgsql;


-- ── 3. Retry stale dispatches (>3h without snapshot) ───────────────────────

CREATE OR REPLACE FUNCTION retry_stale_snapshots()
RETURNS INTEGER AS $$
DECLARE
    _count INTEGER;
    _active_stages TEXT[] := ARRAY[
        'Factorial Project Alignment started',
        'Demo Booked', 'Meeting Booked',
        'MEDDPICC Criteria Validation Started',
        'Economical Allignment Started',
        'Pricing and Packaging', 'Pricing & Packaging',
        'Contract Sent',
        'Discovery', 'Product Alignment',
        'Pre-qualified', 'Engaged', 'Attempting to contact',
        'Associating the partner', 'Research & Outreach',
        'New', 'New Deals', 'Opportunity detected',
        'On Hold', 'Nurturing', 'To reschedule',
        'Sales Nurturing', 'Connected - Not Engaged'
    ];
BEGIN
    WITH stale AS (
        SELECT dc.id
        FROM deal_confirmations dc
        JOIN deals d ON d.id = dc.deal_id
        WHERE dc.front_deal_triggered_at IS NOT NULL
          AND dc.front_deal_triggered_at < now() - interval '3 hours'
          AND dc.calls_ready
          AND dc.emails_ready
          AND dc.notes_ready
          AND d.deal_stage = ANY(_active_stages)
          AND (
              NOT EXISTS (
                  SELECT 1 FROM front_deal_snapshots s
                  WHERE s.deal_id = dc.deal_id
              )
              OR (
                  SELECT MAX(s.created_at) FROM front_deal_snapshots s
                  WHERE s.deal_id = dc.deal_id
              ) < dc.front_deal_triggered_at
          )
        LIMIT 50
    )
    UPDATE deal_confirmations
    SET front_deal_triggered_at = NULL
    WHERE id IN (SELECT id FROM stale);

    GET DIAGNOSTICS _count = ROW_COUNT;
    RETURN _count;
END;
$$ LANGUAGE plpgsql;


-- ── 4. Retry stale context syncs (emails/calls/notes stuck) ────────────────

CREATE OR REPLACE FUNCTION retry_stale_context_syncs()
RETURNS INTEGER AS $$
DECLARE
    _pat   TEXT;
    _rec   RECORD;
    _count INTEGER := 0;
    _active_stages TEXT[] := ARRAY[
        'Factorial Project Alignment started',
        'Demo Booked', 'Meeting Booked',
        'MEDDPICC Criteria Validation Started',
        'Economical Allignment Started',
        'Pricing and Packaging', 'Pricing & Packaging',
        'Contract Sent',
        'Discovery', 'Product Alignment',
        'Pre-qualified', 'Engaged', 'Attempting to contact',
        'Associating the partner', 'Research & Outreach',
        'New', 'New Deals', 'Opportunity detected',
        'On Hold', 'Nurturing', 'To reschedule',
        'Sales Nurturing', 'Connected - Not Engaged'
    ];
BEGIN
    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat'
    LIMIT 1;

    IF _pat IS NULL THEN
        RAISE WARNING 'github_pat not found in vault';
        RETURN 0;
    END IF;

    FOR _rec IN
        SELECT dc.deal_id, dc.hs_deal_id
        FROM deal_confirmations dc
        JOIN deals d ON d.id = dc.deal_id
        WHERE (NOT dc.calls_ready OR NOT dc.emails_ready OR NOT dc.notes_ready)
          AND dc.updated_at < now() - interval '6 hours'
          AND d.deal_stage = ANY(_active_stages)
          AND LOWER(d.deal_name) NOT LIKE '%session%'
        ORDER BY dc.updated_at ASC
        LIMIT 10
    LOOP
        PERFORM net.http_post(
            url     := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/sync_deal_context.yml/dispatches',
            headers := jsonb_build_object(
                'Authorization', 'Bearer ' || _pat,
                'Accept', 'application/vnd.github.v3+json',
                'Content-Type', 'application/json'
            ),
            body    := jsonb_build_object(
                'ref', 'main',
                'inputs', jsonb_build_object(
                    'deal_uuid', _rec.deal_id::text,
                    'hs_deal_id', _rec.hs_deal_id
                )
            )
        );

        _count := _count + 1;
    END LOOP;

    RETURN _count;
END;
$$ LANGUAGE plpgsql;


-- ── 5. Schedule pg_cron jobs ───────────────────────────────────────────────

SELECT cron.schedule(
    'dispatch_pending_snapshots',
    '*/10 * * * *',
    'SELECT dispatch_pending_snapshots()'
);

SELECT cron.schedule(
    'retry_stale_snapshots',
    '0 */2 * * *',
    'SELECT retry_stale_snapshots()'
);

SELECT cron.schedule(
    'retry_stale_context_syncs',
    '30 */2 * * *',
    'SELECT retry_stale_context_syncs()'
);
