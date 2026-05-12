-- ============================================================================
-- Migration 009: Unified context sync
-- ============================================================================
--
-- Replaces parallel build_deal_context + sync_calls with a single unified
-- sync_deal_context pipeline. Fixes:
--
--   1. Race condition — parallel writes to deal_context from two workflows
--   2. check_calls_ready count mismatch (compared HubSpot total vs table count,
--      but only auditable calls are in the table → never matched)
--   3. trg_dc_context_updated too broad (fired on ANY deal_context change,
--      couldn't distinguish email/note/call/audit writes)
--
-- Drops from 007: trg_deal_counts_changed, trg_dc_context_updated,
--                  trg_deal_calls_changed
-- Replaces with:  trg_deal_sync_context (single trigger, single workflow)
-- ============================================================================


-- ── 1. Atomic append function ────────────────────────────────────────────
-- Prevents data loss when multiple processes append to deal_context.

CREATE OR REPLACE FUNCTION append_deal_context(p_deal_id UUID, p_text TEXT)
RETURNS VOID AS $$
BEGIN
    UPDATE deals
    SET deal_context = CASE
        WHEN deal_context IS NULL OR deal_context = '' THEN p_text
        ELSE deal_context || E'\n\n' || p_text
    END
    WHERE id = p_deal_id;
END;
$$ LANGUAGE plpgsql;


-- ── 2. Rewrite check_calls_ready ─────────────────────────────────────────
-- Old version compared HubSpot count (numero_de_calls) vs calls table count.
-- Only auditable calls go into the table, so counts never matched.
-- New version: 0 unaudited auditable calls = ready.

CREATE OR REPLACE FUNCTION check_calls_ready(p_deal_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    unaudited INTEGER;
BEGIN
    SELECT count(*) INTO unaudited
    FROM calls c
    WHERE c.deal_id = p_deal_id
      AND c.rol IS NOT NULL
      AND LENGTH(COALESCE(c.transcript, '')) >= 200
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


-- ── 3. Drop obsolete triggers from 007 ──────────────────────────────────

DROP TRIGGER IF EXISTS trg_deal_counts_changed ON deals;
DROP FUNCTION IF EXISTS dispatch_build_deal_context();

DROP TRIGGER IF EXISTS trg_dc_context_updated ON deals;
DROP FUNCTION IF EXISTS dc_on_context_updated();

DROP TRIGGER IF EXISTS trg_deal_calls_changed ON deals;
DROP FUNCTION IF EXISTS dispatch_sync_calls();


-- ── 4. New unified trigger ──────────────────────────────────────────────
-- Fires when any engagement count changes. Dispatches ONE workflow that
-- handles emails, notes, and calls sequentially in chronological order.

CREATE OR REPLACE FUNCTION dispatch_sync_deal_context()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
    _emails_changed BOOLEAN := FALSE;
    _notes_changed  BOOLEAN := FALSE;
    _calls_changed  BOOLEAN := FALSE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        _emails_changed := COALESCE(NEW.numero_de_emails, 0) > 0;
        _notes_changed  := COALESCE(NEW.numero_de_notas, 0) > 0;
        _calls_changed  := COALESCE(NEW.numero_de_calls, 0) > 0;
    ELSE
        _emails_changed := NEW.numero_de_emails IS DISTINCT FROM OLD.numero_de_emails;
        _notes_changed  := NEW.numero_de_notas IS DISTINCT FROM OLD.numero_de_notas;
        _calls_changed  := NEW.numero_de_calls IS DISTINCT FROM OLD.numero_de_calls;
    END IF;

    IF NOT (_emails_changed OR _notes_changed OR _calls_changed) THEN
        RETURN NEW;
    END IF;

    UPDATE deal_confirmations
    SET emails_ready = CASE WHEN _emails_changed THEN FALSE ELSE emails_ready END,
        notes_ready  = CASE WHEN _notes_changed  THEN FALSE ELSE notes_ready  END,
        calls_ready  = CASE WHEN _calls_changed  THEN FALSE ELSE calls_ready  END,
        front_deal_triggered_at = NULL
    WHERE deal_id = NEW.id;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/sync_deal_context.yml/dispatches',
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

-- Created DISABLED — enable after backfills complete
CREATE TRIGGER trg_deal_sync_context
    AFTER INSERT OR UPDATE ON deals
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_sync_deal_context();

ALTER TABLE deals DISABLE TRIGGER trg_deal_sync_context;
