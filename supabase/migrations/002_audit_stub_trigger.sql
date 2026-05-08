-- ============================================================================
-- Trigger 1: When a call is inserted, create an audit stub in the correct table
-- ============================================================================

CREATE OR REPLACE FUNCTION create_audit_stub()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.rol = 'PBD' THEN
        INSERT INTO pbd_audits (call_ref, call_id, deal_ref, crm_id, hs_deal_id, owner_name)
        VALUES (NEW.id, NEW.call_id, NEW.deal_id, NEW.crm_id, NEW.hs_deal_id, NEW.owner_nombre);
    ELSIF NEW.rol = 'PAE' THEN
        INSERT INTO pae_audits (call_ref, call_id, deal_ref, crm_id, hs_deal_id, owner_name)
        VALUES (NEW.id, NEW.call_id, NEW.deal_id, NEW.crm_id, NEW.hs_deal_id, NEW.owner_nombre);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_call_inserted
    AFTER INSERT ON calls
    FOR EACH ROW
    EXECUTE FUNCTION create_audit_stub();


-- ============================================================================
-- Trigger 2: When an audit stub is created, dispatch the audit workflow
-- ============================================================================
-- Prerequisites:
--   1. Enable pg_net extension: CREATE EXTENSION IF NOT EXISTS pg_net;
--   2. Store GitHub PAT in Supabase Vault:
--        SELECT vault.create_secret('github_pat', 'ghp_xxx...');
--   3. Set repo in app config (Supabase Dashboard → Settings → Database → App Settings):
--        app.settings.github_repo = 'owner/claudio'
-- ============================================================================

CREATE OR REPLACE FUNCTION dispatch_audit_workflow()
RETURNS TRIGGER AS $$
DECLARE
    _pat TEXT;
    _repo TEXT := current_setting('app.settings.github_repo', true);
BEGIN
    IF NEW.win_rate_score IS NOT NULL THEN
        RETURN NEW;
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

CREATE TRIGGER trg_pbd_audit_stub_created
    AFTER INSERT ON pbd_audits
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_audit_workflow();

CREATE TRIGGER trg_pae_audit_stub_created
    AFTER INSERT ON pae_audits
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_audit_workflow();
