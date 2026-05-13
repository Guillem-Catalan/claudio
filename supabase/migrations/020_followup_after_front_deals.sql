-- Trigger: dispatch pae_followup.yml AFTER front_deal_snapshots is generated,
-- but only if pae_followup_pending is true for that deal.
-- This ensures the follow-up has access to the latest synthesized snapshot.

CREATE OR REPLACE FUNCTION dispatch_pae_followup_after_snapshot()
RETURNS TRIGGER AS $$
DECLARE
    _call_ref UUID;
    _pat      TEXT;
    _repo     TEXT;
    _deal_uuid UUID;
BEGIN
    -- Resolve deal UUID from hs_deal_id
    SELECT id INTO _deal_uuid
    FROM deals
    WHERE hs_deal_id = NEW.hs_deal_id
    LIMIT 1;

    IF _deal_uuid IS NULL THEN
        RETURN NEW;
    END IF;

    -- Check if there's a pending follow-up for this deal
    SELECT pae_followup_call_ref INTO _call_ref
    FROM deal_confirmations
    WHERE deal_id = _deal_uuid
      AND pae_followup_pending = TRUE;

    IF _call_ref IS NULL THEN
        RETURN NEW;
    END IF;

    -- Clear the flag before dispatching
    UPDATE deal_confirmations
    SET pae_followup_pending = FALSE,
        updated_at = NOW()
    WHERE deal_id = _deal_uuid;

    -- Get GitHub PAT from vault
    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    IF _pat IS NULL THEN
        RAISE WARNING 'github_pat not found in vault';
        RETURN NEW;
    END IF;

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/pae_followup.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object('call_ref', _call_ref::text)
        )
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_followup_after_front_deals
    AFTER INSERT ON front_deal_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_pae_followup_after_snapshot();
