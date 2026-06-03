-- ============================================================================
-- Migration 046: Unified Run Deals pipeline
-- ============================================================================
-- Replaces the async trigger/flag/cron chain with a single context_stale flag.
-- Run Deals (hourly) reads stale deals and processes them end-to-end:
--   sync → atlas → context → snapshot
-- ============================================================================

-- ── 1. New column on deals ──────────────────────────────────────────────

ALTER TABLE deals ADD COLUMN IF NOT EXISTS context_stale BOOLEAN DEFAULT FALSE;

-- ── 2. New trigger: mark context_stale on engagement count change ───────
-- Replaces trg_deal_sync_context (which dispatched a separate workflow)

CREATE OR REPLACE FUNCTION mark_context_stale()
RETURNS TRIGGER AS $$
BEGIN
  IF (OLD.numero_de_emails IS DISTINCT FROM NEW.numero_de_emails
      OR OLD.numero_de_notas IS DISTINCT FROM NEW.numero_de_notas
      OR OLD.numero_de_calls IS DISTINCT FROM NEW.numero_de_calls
      OR OLD.numero_de_meetings IS DISTINCT FROM NEW.numero_de_meetings)
  THEN
    NEW.context_stale := TRUE;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mark_context_stale
  BEFORE UPDATE ON deals
  FOR EACH ROW
  EXECUTE FUNCTION mark_context_stale();

-- ── 3. New trigger: mark deal stale when Modjo inserts an auditable call ─
-- Replaces trg_dc_call_inserted (which set calls_ready=FALSE on deal_confirmations)

CREATE OR REPLACE FUNCTION mark_deal_stale_on_call()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.deal_id IS NOT NULL
     AND NEW.transcript IS NOT NULL
     AND LENGTH(NEW.transcript) >= 200
     AND NEW.rol IS NOT NULL
  THEN
    UPDATE deals SET context_stale = TRUE
    WHERE id = NEW.deal_id AND (context_stale IS NOT TRUE);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mark_deal_stale_on_call
  AFTER INSERT ON calls
  FOR EACH ROW
  EXECUTE FUNCTION mark_deal_stale_on_call();

-- ── 4. Disable old triggers ─────────────────────────────────────────────

ALTER TABLE deals DISABLE TRIGGER trg_deal_sync_context;
ALTER TABLE calls DISABLE TRIGGER trg_dc_call_inserted;
ALTER TABLE pbd_audits DISABLE TRIGGER trg_dc_audit_completed_pbd;
ALTER TABLE pae_audits DISABLE TRIGGER trg_dc_audit_completed_pae;
ALTER TABLE deal_confirmations DISABLE TRIGGER trg_dc_snapshot_ready;
ALTER TABLE deals DISABLE TRIGGER trg_dc_deal_created;
ALTER TABLE atlas DISABLE TRIGGER trg_atlas_stub_created;
ALTER TABLE atlas DISABLE TRIGGER trg_dc_atlas_completed;

-- ── 5. Remove old pg_cron jobs ──────────────────────────────────────────

SELECT cron.unschedule('dispatch_pending_snapshots');
SELECT cron.unschedule('retry_stale_snapshots');
SELECT cron.unschedule('retry_stale_context_syncs');

-- ── 6. Update sync_deals_hourly to dispatch run_deals.yml ───────────────

CREATE OR REPLACE FUNCTION dispatch_run_deals()
RETURNS void AS $$
DECLARE
  github_pat TEXT;
  _repo TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  _repo := current_setting('app.settings.github_repo', true);
  IF _repo IS NULL OR _repo = '' THEN
    _repo := 'Guillem-Catalan/claudio';
  END IF;

  PERFORM net.http_post(
    url := 'https://api.github.com/repos/' || _repo || '/actions/workflows/run_deals.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || github_pat,
      'Accept', 'application/vnd.github.v3+json',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object('ref', 'main')
  );
END;
$$ LANGUAGE plpgsql;

SELECT cron.unschedule('sync_deals_hourly');
SELECT cron.schedule('run_deals_hourly', '0 * * * *', 'SELECT dispatch_run_deals()');
