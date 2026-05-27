-- ============================================================================
-- Migration 030: Dispatch pbd_snapshot.yml when deal is in PBD stage
-- ============================================================================
-- Extends dc_on_snapshot_ready() to also dispatch pbd_snapshot.yml
-- when the deal's current stage is a PBD stage.
-- ============================================================================

CREATE OR REPLACE FUNCTION dc_on_snapshot_ready()
RETURNS TRIGGER AS $$
DECLARE
    _pat   TEXT;
    _repo  TEXT;
    _stage TEXT;
    _is_pbd BOOLEAN := FALSE;
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

    -- Check if deal is in a PBD stage
    SELECT deal_stage INTO _stage
    FROM deals
    WHERE id = NEW.deal_id;

    IF _stage IN (
        'Research & Outreach', 'Pre-qualified', 'Associating the partner',
        'Engaged', 'Attempting to contact', 'Nurturing', 'New',
        'Demo Booked', 'New Deals', 'To reschedule',
        'Opportunity detected', 'Meeting Booked', 'Discovery',
        'Sales Nurturing', 'Client Contacted', 'Connected - Not Engaged',
        'Long Nurturing', 'Attempted to contact', 'Hot Nurturing',
        'Meeting scheduled'
    ) THEN
        _is_pbd := TRUE;
    END IF;

    -- Always dispatch front_deals snapshot
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

    -- Also dispatch PBD snapshot if deal is in PBD stage
    IF _is_pbd THEN
        PERFORM net.http_post(
            url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/pbd_snapshot.yml/dispatches',
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
    END IF;

    UPDATE deal_confirmations
    SET front_deal_triggered_at = now()
    WHERE id = NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
