-- ============================================================================
-- Migration 047: meeting_evaluations table + weekly reports pg_cron
-- ============================================================================
-- meeting_evaluations: per-meeting quality scoring by type (first_demo,
-- follow_up, closing). Filled by the weekly report pipeline, NOT by triggers.
-- pg_cron: dispatch one weekly_tl_reports.yml per active PAE on Monday 05:00 UTC.
-- ============================================================================

-- ── 1. Table ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meeting_evaluations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id UUID REFERENCES calls(id),
  deal_id UUID REFERENCES deals(id),
  pae_audit_id UUID,
  meeting_type TEXT NOT NULL CHECK (meeting_type IN ('first_demo', 'follow_up', 'closing')),
  meeting_date TIMESTAMPTZ,
  has_transcript BOOLEAN DEFAULT true,
  owner_email TEXT,
  owner_name TEXT,
  deal_name TEXT,
  deal_stage TEXT,
  amount NUMERIC,
  partner TEXT,

  meeting_summary TEXT,
  quality_score NUMERIC,

  m_score NUMERIC, m_text TEXT,
  e_score NUMERIC, e_text TEXT,
  dc_score NUMERIC, dc_text TEXT,
  dp_score NUMERIC, dp_text TEXT,
  i_score NUMERIC, i_text TEXT,
  c_score NUMERIC, c_text TEXT,

  blockers_resolved TEXT,
  blockers_remaining TEXT,
  meddic_advancement TEXT,
  engagement_quality TEXT,

  negotiation_assessment TEXT,
  pricing_handling TEXT,
  objection_handling TEXT,
  close_timeline TEXT,

  signals TEXT,
  improvements TEXT,
  next_step TEXT,
  coaching_note TEXT,

  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE meeting_evaluations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON meeting_evaluations FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON meeting_evaluations FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service all" ON meeting_evaluations FOR ALL TO service_role USING (true);

-- ── 2. pg_cron: dispatch weekly reports ─────────────────────────────────

CREATE OR REPLACE FUNCTION dispatch_weekly_reports()
RETURNS void AS $$
DECLARE
  github_pat TEXT;
  _repo TEXT;
  _pae TEXT;
  _pae_list TEXT[] := ARRAY[
    'xavier.fortuny@factorial.co',
    'jose.donis@factorial.co',
    'pol.bartolome@factorial.co',
    'mireia.serrano@factorial.co',
    'joan.lorenzo@factorial.co',
    'joan.balana@factorial.co',
    'carlos.sanchez@factorial.co',
    'david.clemente@factorial.co',
    'nerea.urien@factorial.co',
    'juan.martinez@factorial.co',
    'alejandro.soto@factorial.co',
    'christian.lombardo@factorial.co',
    'edoardo.rapezzi@factorial.co',
    'emilio.fabbro@factorial.co'
  ];
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

  FOREACH _pae IN ARRAY _pae_list
  LOOP
    PERFORM net.http_post(
      url := 'https://api.github.com/repos/' || _repo || '/actions/workflows/weekly_tl_reports.yml/dispatches',
      headers := jsonb_build_object(
        'Authorization', 'Bearer ' || github_pat,
        'Accept', 'application/vnd.github.v3+json',
        'Content-Type', 'application/json'
      ),
      body := jsonb_build_object(
        'ref', 'main',
        'inputs', jsonb_build_object('pae_email', _pae)
      )
    );
  END LOOP;
END;
$$ LANGUAGE plpgsql;

SELECT cron.schedule('weekly_tl_reports', '0 5 * * 1', 'SELECT dispatch_weekly_reports()');
