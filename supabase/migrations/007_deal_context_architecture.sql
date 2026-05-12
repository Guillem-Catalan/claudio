-- ============================================================================
-- Migration 007: Deal Context Architecture
-- ============================================================================
--
-- Replaces raw email/note storage with pre-built deal_context column on deals.
-- Drops obsolete triggers from 003 (email processing, note counting) and
-- 004 (sync_emails/notes dispatch). Replaces them with:
--   - trg_deal_counts_changed → dispatch build_deal_context.yml (emails/notes)
--   - trg_deal_calls_changed → dispatch sync_calls.yml (calls)
--   - trg_dc_context_updated → set emails_ready/notes_ready = TRUE
--
-- Runs AFTER 001–006. All DROP statements use IF EXISTS for safety.
-- ============================================================================


-- ── 1. Add deal_context column ────────────────────────────────────────────

ALTER TABLE deals ADD COLUMN IF NOT EXISTS deal_context TEXT DEFAULT '';


-- ── 2. Drop obsolete triggers from 003 ───────────────────────────────────

-- Email insert → reset emails_ready (003 §6)
DROP TRIGGER IF EXISTS trg_dc_email_inserted ON emails;
DROP FUNCTION IF EXISTS dc_on_email_inserted();

-- Email insert → dispatch email_processing.yml (003 §6)
DROP TRIGGER IF EXISTS trg_email_inserted_dispatch ON emails;
DROP FUNCTION IF EXISTS dispatch_email_processing();

-- Email processed → check emails_ready (003 §7)
DROP TRIGGER IF EXISTS trg_dc_email_processed ON emails;
DROP FUNCTION IF EXISTS dc_on_email_processed();

-- Note insert → check notes_ready (003 §8)
DROP TRIGGER IF EXISTS trg_dc_note_inserted ON notes;
DROP FUNCTION IF EXISTS dc_on_note_inserted();

-- deals.numero_de_notas changed → re-check notes_ready (003 §9)
DROP TRIGGER IF EXISTS trg_dc_notes_count_updated ON deals;
DROP FUNCTION IF EXISTS dc_on_notes_count_updated();

-- Helper functions (003 §2)
DROP FUNCTION IF EXISTS check_emails_ready(UUID);
DROP FUNCTION IF EXISTS check_notes_ready(UUID);


-- ── 3. Drop obsolete triggers from 004 ───────────────────────────────────

-- sync_emails dispatch — workflow no longer exists
DROP TRIGGER IF EXISTS trg_deal_emails_changed ON deals;
DROP FUNCTION IF EXISTS dispatch_sync_emails();

-- sync_notes dispatch — workflow no longer exists
DROP TRIGGER IF EXISTS trg_deal_notes_changed ON deals;
DROP FUNCTION IF EXISTS dispatch_sync_notes();

-- email_processing dispatch on email insert — workflow no longer exists
DROP TRIGGER IF EXISTS trg_email_inserted ON emails;

-- sync_calls dispatch — will be recreated below with new logic
DROP TRIGGER IF EXISTS trg_deal_calls_changed ON deals;
DROP FUNCTION IF EXISTS dispatch_sync_calls();


-- ── 4. New trigger: deal counts changed → dispatch build_deal_context ─────
-- Fires on INSERT (new deal with existing emails/notes) and UPDATE (counts changed)

CREATE OR REPLACE FUNCTION dispatch_build_deal_context()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
    _type TEXT;
    _emails_changed BOOLEAN;
    _notes_changed  BOOLEAN;
BEGIN
    IF TG_OP = 'INSERT' THEN
        _emails_changed := COALESCE(NEW.numero_de_emails, 0) > 0;
        _notes_changed  := COALESCE(NEW.numero_de_notas, 0) > 0;
    ELSE
        _emails_changed := NEW.numero_de_emails IS DISTINCT FROM OLD.numero_de_emails;
        _notes_changed  := NEW.numero_de_notas IS DISTINCT FROM OLD.numero_de_notas;
    END IF;

    IF NOT _emails_changed AND NOT _notes_changed THEN
        RETURN NEW;
    END IF;

    IF _emails_changed AND _notes_changed THEN
        _type := 'all';
    ELSIF _emails_changed THEN
        _type := 'emails';
    ELSE
        _type := 'notes';
    END IF;

    -- Set readiness flags to FALSE
    IF _emails_changed THEN
        UPDATE deal_confirmations
        SET emails_ready = FALSE, front_deal_triggered_at = NULL
        WHERE deal_id = NEW.id;
    END IF;

    IF _notes_changed THEN
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
    AFTER INSERT OR UPDATE ON deals
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_build_deal_context();


-- ── 5. New trigger: deal_context updated → set emails_ready/notes_ready ───

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


-- ── 6. New trigger: calls count changed → dispatch sync_calls.yml ─────────
-- Fires on INSERT (new deal with calls) and UPDATE (count changed)

CREATE OR REPLACE FUNCTION dispatch_sync_calls()
RETURNS TRIGGER AS $$
DECLARE
    _should_fire BOOLEAN := FALSE;
    _pat  TEXT;
    _repo TEXT;
BEGIN
    IF TG_OP = 'INSERT' AND COALESCE(NEW.numero_de_calls, 0) > 0 THEN
        _should_fire := TRUE;
    ELSIF TG_OP = 'UPDATE' AND NEW.numero_de_calls IS DISTINCT FROM OLD.numero_de_calls THEN
        _should_fire := TRUE;
    END IF;

    IF NOT _should_fire THEN
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
    AFTER INSERT OR UPDATE ON deals
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_sync_calls();
