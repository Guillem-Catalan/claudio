-- ============================================================================
-- 021: audit_demos — Demo evaluation table + PDF dispatch trigger
-- ============================================================================

CREATE TABLE audit_demos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_ref        UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    call_id         TEXT NOT NULL,
    deal_ref        UUID REFERENCES deals(id) ON DELETE SET NULL,
    hs_deal_id      TEXT,
    pae_audit_ref   UUID REFERENCES pae_audits(id) ON DELETE SET NULL,

    -- Metadata
    owner_name      TEXT,
    owner_email     TEXT,
    demo_date       TIMESTAMPTZ,
    company_name    TEXT,
    partner         TEXT,
    deal_name       TEXT,
    deal_stage      TEXT,
    amount          NUMERIC,
    pbd             TEXT,
    pae             TEXT,

    -- Claude output — same keys as front_deal_snapshots
    demo_summary    TEXT,

    m_accumulate    TEXT,
    m_score         NUMERIC,
    e_accumulate    TEXT,
    e_score         NUMERIC,
    dc_accumulate   TEXT,
    dc_score        NUMERIC,
    dp_accumulate   TEXT,
    dp_score        NUMERIC,
    i_accumulate    TEXT,
    i_score         NUMERIC,
    c_accumulate    TEXT,
    c_score         NUMERIC,

    objections      TEXT,
    buyer_signals   TEXT,
    live_blockers   TEXT,
    improvements    TEXT,
    deal_strengths  TEXT,
    next_step       TEXT,

    -- PDF (pending)
    pdf_generated   BOOLEAN DEFAULT FALSE,
    pdf_url         TEXT,

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ────────────────────────────────────────────────────────────────

CREATE INDEX idx_audit_demos_deal_ref ON audit_demos(deal_ref);
CREATE INDEX idx_audit_demos_call_id ON audit_demos(call_id);
CREATE INDEX idx_audit_demos_owner ON audit_demos(owner_email);

-- ── RLS ────────────────────────────────────────────────────────────────────

ALTER TABLE audit_demos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated read" ON audit_demos FOR SELECT TO authenticated USING (true);

-- ── Auto-update updated_at ─────────────────────────────────────────────────

CREATE TRIGGER trg_audit_demos_updated_at BEFORE UPDATE ON audit_demos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Trigger: dispatch PDF workflow on insert ───────────────────────────────

CREATE OR REPLACE FUNCTION dispatch_demo_report()
RETURNS TRIGGER AS $$
DECLARE
    _pat TEXT;
BEGIN
    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    PERFORM net.http_post(
        url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/demo_report.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github.v3+json',
            'Content-Type', 'application/json'
        ),
        body := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'audit_demo_id', NEW.id::TEXT
            )
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_demo_report
    AFTER INSERT ON audit_demos
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_demo_report();
