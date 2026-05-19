-- ============================================================================
-- Migration 025: Re-enable audit stub + completion triggers + meetings count
-- ============================================================================
--
-- 1. Re-enable confirmation chain triggers
-- 2. Add numero_de_meetings column to deals (HubSpot meetings = demos)
-- ============================================================================


-- ── 1. Re-enable triggers for classify→audit pipeline ──────────────────────

ALTER TABLE calls ENABLE TRIGGER trg_call_inserted;
ALTER TABLE pbd_audits ENABLE TRIGGER trg_dc_audit_completed_pbd;
ALTER TABLE pae_audits ENABLE TRIGGER trg_dc_audit_completed_pae;


-- ── 2. Track HubSpot meetings (Google Meet / Teams demos) ─────────────────

ALTER TABLE deals ADD COLUMN IF NOT EXISTS numero_de_meetings INTEGER DEFAULT 0;
