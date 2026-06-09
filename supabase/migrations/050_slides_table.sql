-- ============================================================================
-- Migration 050: Slides table
-- ============================================================================

CREATE TABLE slides (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id           UUID REFERENCES deals(id) ON DELETE CASCADE,
    deal_name         TEXT,
    kind              TEXT NOT NULL DEFAULT 'post_demo',
    status            TEXT NOT NULL DEFAULT 'pending',
    presentation_url  TEXT,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_slides_deal ON slides(deal_id);
CREATE INDEX idx_slides_status ON slides(status);

ALTER TABLE slides ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON slides FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON slides FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service write" ON slides FOR ALL TO service_role USING (true);
