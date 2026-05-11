-- ============================================================================
-- Migration 003: Deal Confirmations triggers + email dispatch trigger
-- ============================================================================
--
-- Builds the full trigger chain:
--   calls INSERT → audit complete → calls_ready
--   emails INSERT → email processed → emails_ready
--   notes INSERT → notes_ready
--   atlas UPDATE → atlas_ready
--   all_ready → dispatch front_deals.yml
-- ============================================================================


-- ── 1. Fix defaults: new deal with no data is "ready" (nothing pending) ────

ALTER TABLE deal_confirmations ALTER COLUMN calls_ready SET DEFAULT TRUE;
ALTER TABLE deal_confirmations ALTER COLUMN emails_ready SET DEFAULT TRUE;
ALTER TABLE deal_confirmations ALTER COLUMN notes_ready SET DEFAULT TRUE;
-- atlas_ready stays DEFAULT FALSE (always needs generation)


-- ── 2. Helper functions ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION check_calls_ready(p_deal_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    expected INTEGER;
    actual   INTEGER;
    unaudited INTEGER;
BEGIN
    SELECT COALESCE(numero_de_calls, 0) INTO expected FROM deals WHERE id = p_deal_id;
    SELECT count(*) INTO actual FROM calls WHERE deal_id = p_deal_id;

    IF actual < expected THEN
        RETURN FALSE;
    END IF;

    SELECT count(*) INTO unaudited
    FROM calls c
    WHERE c.deal_id = p_deal_id
      AND c.rol IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM pbd_audits a
          WHERE a.call_ref = c.id AND a.win_rate_score IS NOT NULL
      )
      AND NOT EXISTS (
          SELECT 1 FROM pae_audits a
          WHERE a.call_ref = c.id AND a.win_rate_score IS NOT NULL
      );

    RETURN unaudited = 0;
END;
$$ LANGUAGE plpgsql STABLE;


CREATE OR REPLACE FUNCTION check_emails_ready(p_deal_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    expected    INTEGER;
    actual      INTEGER;
    unprocessed INTEGER;
BEGIN
    SELECT COALESCE(numero_de_emails, 0) INTO expected FROM deals WHERE id = p_deal_id;
    SELECT count(*) INTO actual FROM emails WHERE deal_id = p_deal_id;

    IF actual < expected THEN
        RETURN FALSE;
    END IF;

    SELECT count(*) INTO unprocessed
    FROM emails
    WHERE deal_id = p_deal_id AND email_summary IS NULL;

    RETURN unprocessed = 0;
END;
$$ LANGUAGE plpgsql STABLE;


CREATE OR REPLACE FUNCTION check_notes_ready(p_deal_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    expected INTEGER;
    actual   INTEGER;
BEGIN
    SELECT COALESCE(numero_de_notas, 0) INTO expected FROM deals WHERE id = p_deal_id;
    SELECT count(*) INTO actual FROM notes WHERE deal_id = p_deal_id;
    RETURN actual >= expected;
END;
$$ LANGUAGE plpgsql STABLE;


-- ── 3. Deal INSERT → create deal_confirmations row ─────────────────────────

CREATE OR REPLACE FUNCTION dc_on_deal_created()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO deal_confirmations (deal_id, hs_deal_id)
    VALUES (NEW.id, NEW.deal_id)
    ON CONFLICT (deal_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_deal_created
    AFTER INSERT ON deals
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_deal_created();


-- ── 4. Call INSERT → reset calls_ready ─────────────────────────────────────

CREATE OR REPLACE FUNCTION dc_on_call_inserted()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE deal_confirmations
    SET calls_ready = FALSE,
        front_deal_triggered_at = NULL
    WHERE deal_id = NEW.deal_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_call_inserted
    AFTER INSERT ON calls
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_call_inserted();


-- ── 5. Audit completed → check calls_ready ─────────────────────────────────

CREATE OR REPLACE FUNCTION dc_on_audit_completed()
RETURNS TRIGGER AS $$
DECLARE
    _deal_id UUID;
BEGIN
    IF NEW.win_rate_score IS NULL OR OLD.win_rate_score IS NOT NULL THEN
        RETURN NEW;
    END IF;

    SELECT deal_id INTO _deal_id FROM calls WHERE id = NEW.call_ref;

    IF _deal_id IS NOT NULL AND check_calls_ready(_deal_id) THEN
        UPDATE deal_confirmations
        SET calls_ready = TRUE
        WHERE deal_id = _deal_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_audit_completed_pbd
    AFTER UPDATE ON pbd_audits
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_audit_completed();

CREATE TRIGGER trg_dc_audit_completed_pae
    AFTER UPDATE ON pae_audits
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_audit_completed();


-- ── 6. Email INSERT → reset emails_ready + dispatch email_processing ───────

CREATE OR REPLACE FUNCTION dc_on_email_inserted()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE deal_confirmations
    SET emails_ready = FALSE,
        front_deal_triggered_at = NULL
    WHERE deal_id = NEW.deal_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_email_inserted
    AFTER INSERT ON emails
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_email_inserted();

-- Dispatch email_processing.yml (was only in Supabase, not in migrations)
CREATE OR REPLACE FUNCTION dispatch_email_processing()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
BEGIN
    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/email_processing.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object('email_id', NEW.id::text)
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_email_inserted_dispatch
    AFTER INSERT ON emails
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_email_processing();


-- ── 7. Email processed → check emails_ready ───────────────────────────────

CREATE OR REPLACE FUNCTION dc_on_email_processed()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.email_summary IS NULL OR OLD.email_summary IS NOT NULL THEN
        RETURN NEW;
    END IF;

    IF check_emails_ready(NEW.deal_id) THEN
        UPDATE deal_confirmations
        SET emails_ready = TRUE
        WHERE deal_id = NEW.deal_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_email_processed
    AFTER UPDATE ON emails
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_email_processed();


-- ── 8. Note INSERT → check notes_ready ─────────────────────────────────────

CREATE OR REPLACE FUNCTION dc_on_note_inserted()
RETURNS TRIGGER AS $$
BEGIN
    IF check_notes_ready(NEW.deal_id) THEN
        UPDATE deal_confirmations
        SET notes_ready = TRUE
        WHERE deal_id = NEW.deal_id;
    ELSE
        UPDATE deal_confirmations
        SET notes_ready = FALSE,
            front_deal_triggered_at = NULL
        WHERE deal_id = NEW.deal_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_note_inserted
    AFTER INSERT ON notes
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_note_inserted();


-- ── 9. deals.numero_de_notas changed → re-check notes_ready ───────────────

CREATE OR REPLACE FUNCTION dc_on_notes_count_updated()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.numero_de_notas IS NOT DISTINCT FROM OLD.numero_de_notas THEN
        RETURN NEW;
    END IF;

    IF check_notes_ready(NEW.id) THEN
        UPDATE deal_confirmations
        SET notes_ready = TRUE
        WHERE deal_id = NEW.id;
    ELSE
        UPDATE deal_confirmations
        SET notes_ready = FALSE,
            front_deal_triggered_at = NULL
        WHERE deal_id = NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_notes_count_updated
    AFTER UPDATE ON deals
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_notes_count_updated();


-- ── 10. Atlas completed → atlas_ready for all company deals ────────────────

CREATE OR REPLACE FUNCTION dc_on_atlas_completed()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.company_context IS NULL THEN
        RETURN NEW;
    END IF;

    UPDATE deal_confirmations dc
    SET atlas_ready = TRUE
    FROM deals d
    WHERE dc.deal_id = d.id
      AND d.atlas_id = NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_atlas_completed
    AFTER INSERT OR UPDATE ON atlas
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_atlas_completed();


-- ── 11. Snapshot ready → dispatch front_deals.yml ──────────────────────────

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
        _repo := 'guillemcatalan/claudio';
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

CREATE TRIGGER trg_dc_snapshot_ready
    AFTER UPDATE ON deal_confirmations
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_snapshot_ready();
