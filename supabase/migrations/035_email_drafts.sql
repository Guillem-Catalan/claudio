-- ============================================================================
-- Migration 035: Email Drafts table
-- ============================================================================
-- AI-generated follow-up emails per deal.
-- Persist until new deal activity arrives (no cron cleanup).
-- 'copied' rows kept as usage benchmark.
-- ============================================================================

CREATE TABLE email_drafts (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id              UUID REFERENCES deals(id) ON DELETE CASCADE,
    deal_name            TEXT,
    recipient            TEXT,
    send_when            TEXT,
    reason               TEXT,
    subject              TEXT,
    body                 TEXT,
    status               TEXT DEFAULT 'draft',
    context_snapshot_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT now(),
    copied_at            TIMESTAMPTZ
);

CREATE INDEX idx_email_drafts_deal ON email_drafts(deal_id);

ALTER TABLE email_drafts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read"   ON email_drafts FOR SELECT TO anon USING (true);
CREATE POLICY "Anon insert" ON email_drafts FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "Anon update" ON email_drafts FOR UPDATE TO anon USING (true);
CREATE POLICY "Service all" ON email_drafts FOR ALL TO service_role USING (true);
