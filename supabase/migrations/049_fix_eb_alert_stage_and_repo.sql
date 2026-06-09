-- ============================================================================
-- Migration 049: Fix EB alert trigger — add stage variant + fix repo URL
-- ============================================================================

CREATE OR REPLACE FUNCTION dispatch_eb_alert()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    _pat TEXT;
    _repo TEXT;
BEGIN
    IF OLD.deal_stage IS NOT DISTINCT FROM NEW.deal_stage THEN
        RETURN NEW;
    END IF;

    IF NEW.deal_stage NOT IN (
        'Pricing and Packaging',
        'Pricing & Packaging',
        'Economical Allignment Started',
        'Economical Alignment Started'
    ) THEN
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
        url := 'https://api.github.com/repos/' || _repo || '/actions/workflows/eb_alert.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github.v3+json',
            'Content-Type', 'application/json'
        ),
        body := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'deal_uuid', NEW.id::TEXT,
                'deal_id', NEW.deal_id
            )
        )
    );

    RETURN NEW;
END;
$$;
