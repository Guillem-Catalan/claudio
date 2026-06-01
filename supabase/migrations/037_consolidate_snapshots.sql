-- ============================================================================
-- Migration 037: Consolidate snapshot pipeline
-- ============================================================================
--
-- front_deals.yml now runs forecast + PBD BANT inline.
-- No need for separate front_forecast.yml or pbd_snapshot.yml dispatches.
--
-- Changes:
--   1. Drop trg_front_deal_forecast (no separate forecast workflow)
--   2. Simplify dc_on_snapshot_ready (only dispatch front_deals.yml, no pbd)
--   3. Fix repo URL in dispatch_pending_snapshots (was pointing to suspended account)
--   4. Fix repo URL in retry_stale_context_syncs (same issue)
-- ============================================================================


-- ── 1. Drop forecast trigger ─────────────────────────────────────────────
-- front_deals now computes close_probability inline before inserting the
-- snapshot, so it's never NULL on INSERT.

DROP TRIGGER IF EXISTS trg_front_deal_forecast ON front_deal_snapshots;
DROP FUNCTION IF EXISTS dispatch_front_forecast();


-- ── 2. Simplify dc_on_snapshot_ready ─────────────────────────────────────
-- Remove PBD snapshot dispatch (now handled inline by front_deals).

CREATE OR REPLACE FUNCTION dc_on_snapshot_ready()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
BEGIN
    IF NOT (NEW.calls_ready AND NEW.emails_ready AND NEW.notes_ready AND NEW.atlas_ready) THEN
        RETURN NEW;
    END IF;

    IF NEW.front_deal_triggered_at IS NOT NULL THEN
        RETURN NEW;
    END IF;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'Guillem-Catalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/front_deals.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'deal_uuid', NEW.deal_id::text,
                'hs_deal_id', NEW.hs_deal_id
            )
        )
    );

    UPDATE deal_confirmations
    SET front_deal_triggered_at = now()
    WHERE id = NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── 3. Fix dispatch_pending_snapshots repo URL ───────────────────────────
-- Was hardcoded to guillemcatalan/claudio (suspended account).

CREATE OR REPLACE FUNCTION dispatch_pending_snapshots()
RETURNS INTEGER AS $$
DECLARE
    _pat   TEXT;
    _repo  TEXT;
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

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'Guillem-Catalan/claudio';
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
            url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/front_deals.yml/dispatches',
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


-- ── 4. Fix retry_stale_context_syncs repo URL ────────────────────────────

CREATE OR REPLACE FUNCTION retry_stale_context_syncs()
RETURNS INTEGER AS $$
DECLARE
    _pat   TEXT;
    _repo  TEXT;
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

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'Guillem-Catalan/claudio';
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
            url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/sync_deal_context.yml/dispatches',
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
