-- ============================================================================
-- Migration 033: Briefings table
-- ============================================================================
-- Stores AI-generated meeting briefings per deal.
-- Auto-dispatches briefing.yml workflow on INSERT via pg_net trigger.
-- UI inserts pending rows for ad-hoc generation.
-- ============================================================================

CREATE TABLE briefings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id       UUID REFERENCES deals(id) ON DELETE CASCADE,
    meeting_id    UUID REFERENCES deal_meetings(id) ON DELETE SET NULL,
    deal_name     TEXT,
    meeting_type  TEXT NOT NULL,
    brief         JSONB,
    status        TEXT DEFAULT 'pending',
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_briefings_deal ON briefings(deal_id);
CREATE INDEX idx_briefings_status ON briefings(status);

ALTER TABLE briefings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read"   ON briefings FOR SELECT TO anon USING (true);
CREATE POLICY "Anon insert" ON briefings FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "Service all" ON briefings FOR ALL TO service_role USING (true);

-- ── Dispatch briefing.yml on INSERT with status='pending' ─────────────────

CREATE OR REPLACE FUNCTION dispatch_briefing_workflow()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
BEGIN
    IF NEW.status <> 'pending' OR NEW.brief IS NOT NULL THEN
        RETURN NEW;
    END IF;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'Guillem-Catalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/briefing.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'briefing_id', NEW.id::text,
                'deal_uuid', NEW.deal_id::text,
                'meeting_type', NEW.meeting_type
            )
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_briefing_dispatch
    AFTER INSERT ON briefings
    FOR EACH ROW EXECUTE FUNCTION dispatch_briefing_workflow();
