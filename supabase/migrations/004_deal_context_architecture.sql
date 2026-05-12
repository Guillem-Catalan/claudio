-- ============================================================================
-- Migration 004: Deal Context Architecture
-- ============================================================================
--
-- Adds deal_context column to deals table.
-- Replaces email/note sync triggers with build_deal_context dispatch.
-- Simplifies deal_confirmations: emails_ready/notes_ready now track
-- context readiness, not raw row counts.
-- ============================================================================


-- ── 1. Add deal_context column ────────────────────────────────────────────

ALTER TABLE deals ADD COLUMN IF NOT EXISTS deal_context TEXT DEFAULT '';


-- ── 2. Drop obsolete triggers ─────────────────────────────────────────────

DROP TRIGGER IF EXISTS trg_email_inserted_dispatch ON emails;
DROP TRIGGER IF EXISTS trg_dc_email_inserted ON emails;
DROP TRIGGER IF EXISTS trg_dc_email_processed ON emails;
DROP TRIGGER IF EXISTS trg_dc_note_inserted ON notes;
DROP TRIGGER IF EXISTS trg_dc_notes_count_updated ON deals;

DROP FUNCTION IF EXISTS dispatch_email_processing();
DROP FUNCTION IF EXISTS dc_on_email_inserted();
DROP FUNCTION IF EXISTS dc_on_email_processed();
DROP FUNCTION IF EXISTS dc_on_note_inserted();
DROP FUNCTION IF EXISTS dc_on_notes_count_updated();
DROP FUNCTION IF EXISTS check_emails_ready(UUID);
DROP FUNCTION IF EXISTS check_notes_ready(UUID);


-- ── 3. New trigger: deal counts changed → dispatch build_deal_context ─────

CREATE OR REPLACE FUNCTION dispatch_build_deal_context()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
    _type TEXT;
BEGIN
    -- Determine what changed
    IF NEW.numero_de_emails IS DISTINCT FROM OLD.numero_de_emails
       AND NEW.numero_de_notas IS DISTINCT FROM OLD.numero_de_notas THEN
        _type := 'all';
    ELSIF NEW.numero_de_emails IS DISTINCT FROM OLD.numero_de_emails THEN
        _type := 'emails';
    ELSIF NEW.numero_de_notas IS DISTINCT FROM OLD.numero_de_notas THEN
        _type := 'notes';
    ELSE
        RETURN NEW;
    END IF;

    -- Set readiness flags to FALSE
    IF NEW.numero_de_emails IS DISTINCT FROM OLD.numero_de_emails THEN
        UPDATE deal_confirmations
        SET emails_ready = FALSE, front_deal_triggered_at = NULL
        WHERE deal_id = NEW.id;
    END IF;

    IF NEW.numero_de_notas IS DISTINCT FROM OLD.numero_de_notas THEN
        UPDATE deal_confirmations
        SET notes_ready = FALSE, front_deal_triggered_at = NULL
        WHERE deal_id = NEW.id;
    END IF;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/build_deal_context.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'deal_uuid', NEW.id::text,
                'hs_deal_id', NEW.deal_id,
                'context_type', _type
            )
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_deal_counts_changed
    AFTER UPDATE ON deals
    FOR EACH ROW
    WHEN (
        NEW.numero_de_emails IS DISTINCT FROM OLD.numero_de_emails
        OR NEW.numero_de_notas IS DISTINCT FROM OLD.numero_de_notas
    )
    EXECUTE FUNCTION dispatch_build_deal_context();


-- ── 4. New trigger: deal_context updated → set emails_ready/notes_ready ───

CREATE OR REPLACE FUNCTION dc_on_context_updated()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.deal_context IS NOT DISTINCT FROM OLD.deal_context THEN
        RETURN NEW;
    END IF;

    UPDATE deal_confirmations
    SET emails_ready = TRUE,
        notes_ready = TRUE
    WHERE deal_id = NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_context_updated
    AFTER UPDATE ON deals
    FOR EACH ROW
    WHEN (NEW.deal_context IS DISTINCT FROM OLD.deal_context)
    EXECUTE FUNCTION dc_on_context_updated();


-- ── 5. Update calls trigger: dispatch for numero_de_calls changes ─────────

-- The existing trg_deal_emails_changed, trg_deal_notes_changed,
-- trg_deal_calls_changed triggers should be dropped and replaced.
-- calls dispatch is kept separate because calls go to sync_calls.yml

DROP TRIGGER IF EXISTS trg_deal_emails_changed ON deals;
DROP TRIGGER IF EXISTS trg_deal_notes_changed ON deals;
DROP TRIGGER IF EXISTS trg_deal_calls_changed ON deals;

DROP FUNCTION IF EXISTS dispatch_sync_emails();
DROP FUNCTION IF EXISTS dispatch_sync_notes();

-- Keep dispatch_sync_calls if it exists, or create it
CREATE OR REPLACE FUNCTION dispatch_sync_calls()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
BEGIN
    IF NEW.numero_de_calls IS NOT DISTINCT FROM OLD.numero_de_calls THEN
        RETURN NEW;
    END IF;

    UPDATE deal_confirmations
    SET calls_ready = FALSE, front_deal_triggered_at = NULL
    WHERE deal_id = NEW.id;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/sync_calls.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'deal_uuid', NEW.id::text,
                'hs_deal_id', NEW.deal_id
            )
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_deal_calls_changed
    AFTER UPDATE ON deals
    FOR EACH ROW
    WHEN (NEW.numero_de_calls IS DISTINCT FROM OLD.numero_de_calls)
    EXECUTE FUNCTION dispatch_sync_calls();
