-- ============================================================================
-- Migration 036: Calendar Meetings (Google Calendar mirror)
-- ============================================================================
-- Passive mirror of PAE calendars. Does NOT trigger any pipeline.
-- Used by the UI to show "previsto" meetings in the Hoy tab.
-- Reconciled nightly: unmatched meetings → Slack alert.
-- ============================================================================

CREATE TABLE calendar_meetings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gcal_event_id    TEXT UNIQUE NOT NULL,
    gcal_calendar_id TEXT NOT NULL,
    pae_email        TEXT NOT NULL,
    pae_name         TEXT,
    deal_id          UUID REFERENCES deals(id) ON DELETE SET NULL,
    hs_deal_id       TEXT,
    deal_name        TEXT,
    meeting_start    TIMESTAMPTZ NOT NULL,
    meeting_end      TIMESTAMPTZ,
    title            TEXT,
    attendees        JSONB,
    resolved         BOOLEAN DEFAULT FALSE,
    matched          BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cal_meetings_start ON calendar_meetings(meeting_start);
CREATE INDEX idx_cal_meetings_deal ON calendar_meetings(deal_id);
CREATE INDEX idx_cal_meetings_pae ON calendar_meetings(pae_email);

ALTER TABLE calendar_meetings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON calendar_meetings FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON calendar_meetings FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service write" ON calendar_meetings FOR ALL TO service_role USING (true);
