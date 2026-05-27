-- ============================================================================
-- Migration 031: Deal Meetings table
-- ============================================================================
-- Stores individual meeting records from HubSpot for each deal.
-- Populated during sync_deals from HubSpot meetings API.
-- Used by the UI to show "meetings today" and "follow-up yesterday".
-- ============================================================================

CREATE TABLE deal_meetings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id          UUID REFERENCES deals(id) ON DELETE CASCADE,
    hs_deal_id       TEXT NOT NULL,
    hs_meeting_id    TEXT UNIQUE NOT NULL,
    meeting_start    TIMESTAMPTZ,
    meeting_end      TIMESTAMPTZ,
    title            TEXT,
    outcome          TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_deal_meetings_deal ON deal_meetings(deal_id);
CREATE INDEX idx_deal_meetings_start ON deal_meetings(meeting_start);
CREATE INDEX idx_deal_meetings_hs_deal ON deal_meetings(hs_deal_id);

ALTER TABLE deal_meetings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON deal_meetings FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON deal_meetings FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service write" ON deal_meetings FOR ALL TO service_role USING (true);
