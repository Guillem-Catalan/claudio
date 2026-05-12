-- Add repo fallback to dispatch_audit_workflow, consistent with all other
-- dispatch functions. Without this, _repo is NULL when the app setting
-- isn't configured, and the HTTP call silently does nothing.

CREATE OR REPLACE FUNCTION dispatch_audit_workflow()
RETURNS TRIGGER AS $$
DECLARE
    _pat TEXT;
    _repo TEXT := current_setting('app.settings.github_repo', true);
BEGIN
    IF NEW.win_rate_score IS NOT NULL THEN
        RETURN NEW;
    END IF;

    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    PERFORM net.http_post(
        url := 'https://api.github.com/repos/' || _repo || '/actions/workflows/audit.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object('call_id', NEW.call_id)
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
