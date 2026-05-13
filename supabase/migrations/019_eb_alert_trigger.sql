-- Dispatch EB alert when a deal enters "Pricing and Packaging" stage

CREATE OR REPLACE FUNCTION dispatch_eb_alert()
RETURNS TRIGGER AS $$
DECLARE
    _pat TEXT;
BEGIN
    IF OLD.deal_stage IS NOT DISTINCT FROM NEW.deal_stage THEN
        RETURN NEW;
    END IF;

    IF NEW.deal_stage != 'Pricing and Packaging' THEN
        RETURN NEW;
    END IF;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    PERFORM net.http_post(
        url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/eb_alert.yml/dispatches',
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
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_eb_alert
    AFTER UPDATE ON deals
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_eb_alert();
