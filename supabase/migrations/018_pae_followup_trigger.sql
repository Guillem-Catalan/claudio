-- Trigger: dispatch pae_followup.yml when a PAE Demo call is audited.
-- Fires when win_rate_score transitions from NULL to NOT NULL
-- and the associated call has tag 'Partners - PAE Demo'.

CREATE OR REPLACE FUNCTION dispatch_pae_followup()
RETURNS TRIGGER AS $$
DECLARE
    _tag  TEXT;
    _pat  TEXT;
    _repo TEXT;
BEGIN
    SELECT tag INTO _tag
    FROM calls
    WHERE id = NEW.call_ref;

    IF _tag IS DISTINCT FROM 'Partners - PAE Demo' THEN
        RETURN NEW;
    END IF;

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
            'inputs', jsonb_build_object('call_ref', NEW.call_ref::text)
        )
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pae_followup
    AFTER UPDATE ON pae_audits
    FOR EACH ROW
    WHEN (OLD.win_rate_score IS NULL AND NEW.win_rate_score IS NOT NULL)
    EXECUTE FUNCTION dispatch_pae_followup();
