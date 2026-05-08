-- ============================================================================
-- Claudio — Initial Schema
-- Migrated from Airtable (El Juez) to Supabase (PostgreSQL)
-- ============================================================================

-- ── Extensions ──────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_net" WITH SCHEMA "extensions";


-- ── Enums ───────────────────────────────────────────────────────────────────

CREATE TYPE pbd_status AS ENUM (
    'Sin Empezar',
    'En Progreso',
    'Demo Agendada',
    'Handover Completado'
);

CREATE TYPE pae_status AS ENUM (
    'Sin Empezar',
    'En Progreso'
);

CREATE TYPE call_role AS ENUM ('PBD', 'PAE');

CREATE TYPE subteam AS ENUM ('Santander', 'Telefónica', 'TIM', 'TELEKOM');

CREATE TYPE email_direction AS ENUM ('inbound', 'outbound');

CREATE TYPE framework_status AS ENUM ('Missing', 'Partial', 'Confirmed', 'N/A');

CREATE TYPE red_flag_type AS ENUM (
    'BANT_3_MISSING',
    'NO_ECONOMIC_BUYER',
    'FORECAST_RED',
    'PARTNER_LEVERAGE_1'
);


-- ── Companies ───────────────────────────────────────────────────────────────

CREATE TABLE companies (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crm_id     TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    pbd_owner  TEXT,
    pae_owner  TEXT,
    pbd_status pbd_status DEFAULT 'Sin Empezar',
    pae_status pae_status DEFAULT 'Sin Empezar',

    pbd_analisis_global TEXT,
    handover_notes_pae  TEXT,
    handover_pending    BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Deals ───────────────────────────────────────────────────────────────────

CREATE TABLE deals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         TEXT UNIQUE NOT NULL,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    crm_id          TEXT,

    deal_name       TEXT,
    amount          NUMERIC,
    deal_stage      TEXT,
    forecast_category TEXT,
    close_date      DATE,
    createdate      DATE,
    deal_age_days   INTEGER,
    last_hs_modified  DATE,
    last_contacted_hs DATE,
    contact_count   INTEGER DEFAULT 0,
    contacts_info   TEXT,
    rep_next_step   TEXT,
    rep_probability    NUMERIC,
    stage_probability_hs NUMERIC,

    pbd             TEXT,
    pae             TEXT,
    last_synced     TIMESTAMPTZ,

    demo_booked_entered_partners DATE,
    demo_booked_exited_partners  DATE,
    demo_booked_entered_sdr      DATE,
    demo_booked_exited_sdr       DATE,

    -- Notes (HubSpot notes sync)
    hs_notes          TEXT,
    notes_summary     TEXT,
    notes_last_synced TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Calls ───────────────────────────────────────────────────────────────────

CREATE TABLE calls (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id           TEXT UNIQUE NOT NULL,
    company_id        UUID REFERENCES companies(id) ON DELETE SET NULL,
    deal_id           UUID REFERENCES deals(id) ON DELETE SET NULL,
    crm_id            TEXT,
    hs_deal_id        TEXT,

    titulo            TEXT,
    fecha             TIMESTAMPTZ,
    owner_email       TEXT,
    owner_nombre      TEXT,
    rol               call_role,
    tag               TEXT,
    team              TEXT,
    duracion_segundos INTEGER,
    company_name      TEXT,
    transcript        TEXT,
    subteam           subteam,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── PBD Audits ──────────────────────────────────────────────────────────────

CREATE TABLE pbd_audits (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_ref    UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    call_id     TEXT NOT NULL,
    deal_ref    UUID REFERENCES deals(id) ON DELETE SET NULL,
    crm_id      TEXT,
    hs_deal_id  TEXT,
    owner_name  TEXT,

    -- Scores
    win_rate_score          NUMERIC,
    forecast_flag           TEXT,
    partner_leverage_score  NUMERIC,
    lead_temperature        TEXT,

    -- Discovery
    discovery_level     TEXT,
    discovery_topics    TEXT,
    discovery_breakdown TEXT,

    -- Flags
    red_flags_fired     red_flag_type[],
    slack_alert_fired   BOOLEAN DEFAULT FALSE,

    -- Analysis
    improvement_items_json TEXT,
    deal_context           TEXT,
    deal_status            TEXT,
    biggest_gap            TEXT,
    next_call_objective    TEXT,
    tl_note                TEXT,
    top_coaching_flag      TEXT,
    next_action_rep        TEXT,
    hard_question          TEXT,
    objections             TEXT,
    rep_strengths          TEXT,
    buying_signals         TEXT,
    blockers               TEXT,
    tag_validation         TEXT,

    -- BANT
    bant_budget_status      framework_status,
    bant_budget_confidence  NUMERIC,
    bant_budget_evidence    TEXT,
    bant_authority_status   framework_status,
    bant_authority_confidence NUMERIC,
    bant_authority_evidence TEXT,
    bant_need_status        framework_status,
    bant_need_confidence    NUMERIC,
    bant_need_evidence      TEXT,
    bant_timing_status      framework_status,
    bant_timing_confidence  NUMERIC,
    bant_timing_evidence    TEXT,

    -- Script compliance
    script_opener        TEXT,
    script_industry_pivot TEXT,
    script_close         TEXT,
    two_slot_close       BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── PAE Audits ──────────────────────────────────────────────────────────────

CREATE TABLE pae_audits (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_ref    UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    call_id     TEXT NOT NULL,
    deal_ref    UUID REFERENCES deals(id) ON DELETE SET NULL,
    crm_id      TEXT,
    hs_deal_id  TEXT,
    owner_name  TEXT,

    -- Scores
    win_rate_score          NUMERIC,
    forecast_flag           TEXT,
    partner_leverage_score  NUMERIC,
    lead_temperature        TEXT,

    -- Discovery
    discovery_level     TEXT,
    discovery_topics    TEXT,
    discovery_breakdown TEXT,

    -- Flags
    red_flags_fired     red_flag_type[],
    slack_alert_fired   BOOLEAN DEFAULT FALSE,

    -- Analysis
    improvement_items_json TEXT,
    deal_context           TEXT,
    deal_status            TEXT,
    biggest_gap            TEXT,
    next_call_objective    TEXT,
    tl_note                TEXT,
    top_coaching_flag      TEXT,
    next_action_rep        TEXT,
    hard_question          TEXT,
    objections             TEXT,
    rep_strengths          TEXT,
    buying_signals         TEXT,
    blockers               TEXT,
    tag_validation         TEXT,

    -- MEDDIC
    meddic_metrics_status             framework_status,
    meddic_metrics_confidence         NUMERIC,
    meddic_metrics_evidence           TEXT,
    meddic_economic_buyer_status      framework_status,
    meddic_economic_buyer_confidence  NUMERIC,
    meddic_economic_buyer_evidence    TEXT,
    meddic_decision_criteria_status   framework_status,
    meddic_decision_criteria_confidence NUMERIC,
    meddic_decision_criteria_evidence TEXT,
    meddic_decision_process_status    framework_status,
    meddic_decision_process_confidence NUMERIC,
    meddic_decision_process_evidence  TEXT,
    meddic_champion_status            framework_status,
    meddic_champion_confidence        NUMERIC,
    meddic_champion_evidence          TEXT,
    meddic_competition_status         framework_status,
    meddic_competition_confidence     NUMERIC,
    meddic_competition_evidence       TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Emails ──────────────────────────────────────────────────────────────────

CREATE TABLE emails (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hs_engagement_id TEXT UNIQUE NOT NULL,
    deal_id          UUID REFERENCES deals(id) ON DELETE SET NULL,
    company_id       UUID REFERENCES companies(id) ON DELETE SET NULL,
    hs_deal_id       TEXT,
    crm_id           TEXT,

    date             TIMESTAMPTZ,
    direction        email_direction,
    from_email       TEXT,
    subject          TEXT,
    body             TEXT,
    thread_key       TEXT,
    body_clean       TEXT,
    email_summary    TEXT,
    email_type       TEXT,
    key_people       TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Company Atlas (historical context) ──────────────────────────────────────

CREATE TABLE company_atlas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
    crm_id           TEXT,
    deal_history_raw TEXT,
    company_context  TEXT,
    last_generated   TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Config (key-value store) ────────────────────────────────────────────────

CREATE TABLE config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Deal Confirmations (pipeline orchestrator) ──────────────────────────────

CREATE TABLE deal_confirmations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id      UUID UNIQUE REFERENCES deals(id) ON DELETE CASCADE,
    hs_deal_id   TEXT UNIQUE NOT NULL,

    calls_ready  BOOLEAN DEFAULT FALSE,
    emails_ready BOOLEAN DEFAULT FALSE,
    audit_ready  BOOLEAN DEFAULT FALSE,
    atlas_ready  BOOLEAN DEFAULT FALSE,
    notes_ready  BOOLEAN DEFAULT FALSE,

    all_ready    BOOLEAN GENERATED ALWAYS AS (
        calls_ready AND emails_ready AND audit_ready AND atlas_ready AND notes_ready
    ) STORED,

    front_deal_triggered_at TIMESTAMPTZ,
    last_reset_at           TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Front Deal Snapshots ────────────────────────────────────────────────────

CREATE TABLE front_deal_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(id) ON DELETE SET NULL,
    hs_deal_id          TEXT NOT NULL,
    snapshot_date       DATE NOT NULL,

    deal_name           TEXT,
    crm_id              TEXT,
    deal_age            INTEGER,
    stage               TEXT,
    mrr                 NUMERIC,
    hs_forecast_category TEXT,
    pbd                 TEXT,
    pae                 TEXT,

    deal_summary        TEXT,

    m_accumulate TEXT,  m_score  NUMERIC,
    e_accumulate TEXT,  e_score  NUMERIC,
    dc_accumulate TEXT, dc_score NUMERIC,
    dp_accumulate TEXT, dp_score NUMERIC,
    i_accumulate TEXT,  i_score  NUMERIC,
    c_accumulate TEXT,  c_score  NUMERIC,

    objections          TEXT,
    buyer_signals       TEXT,
    live_blockers       TEXT,
    improvements        TEXT,
    deal_strengths      TEXT,
    next_step           TEXT,

    close_probability   NUMERIC,
    claudio_forecast    TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(hs_deal_id, snapshot_date)
);


-- ── Front Rep Snapshots ─────────────────────────────────────────────────────

CREATE TABLE front_rep_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rep_email     TEXT NOT NULL,
    rep_name      TEXT,
    rol           call_role,
    snapshot_date DATE,
    partner       TEXT,
    deal_ref      UUID REFERENCES deals(id) ON DELETE SET NULL,
    hs_deal_id    TEXT,
    stage         TEXT,

    improvements    TEXT,
    strengths       TEXT,
    coaching_flags  TEXT,
    tl_notes        TEXT,
    next_step       TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Front Rep Aggregates ────────────────────────────────────────────────────

CREATE TABLE front_rep_aggregates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rep_email     TEXT NOT NULL,
    rep_name      TEXT,
    rol           call_role,
    partner       TEXT,
    deal_ref      UUID REFERENCES deals(id) ON DELETE SET NULL,
    hs_deal_id    TEXT,
    deal_name     TEXT,
    stage         TEXT,
    last_updated  DATE,

    performance_trend          TEXT,
    improvements_adoption      TEXT,
    coaching_evolution         TEXT,
    objections_tracker         TEXT,
    blockers_tracker           TEXT,
    deal_momentum              TEXT,
    rep_strengths_consolidated TEXT,
    rep_gaps_consolidated      TEXT,
    rep_deal_evolution         TEXT,
    tl_summary                 TEXT,
    next_step                  TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ── Front Rep Briefs ────────────────────────────────────────────────────────

CREATE TABLE front_rep_briefs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rep_email     TEXT NOT NULL,
    rep_name      TEXT,
    rol           call_role,
    partner       TEXT,
    last_updated  DATE,

    total_deals          INTEGER,
    stage_distribution   TEXT,
    closed_deals         TEXT,
    overall_performance  TEXT,
    cross_deal_patterns  TEXT,
    priority_deals       TEXT,
    coaching_brief       TEXT,
    rep_evolution        TEXT,
    next_steps_global    TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);


-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX idx_companies_crm_id ON companies(crm_id);

CREATE INDEX idx_deals_company_id ON deals(company_id);
CREATE INDEX idx_deals_crm_id ON deals(crm_id);
CREATE INDEX idx_deals_deal_stage ON deals(deal_stage);

CREATE INDEX idx_calls_company_id ON calls(company_id);
CREATE INDEX idx_calls_deal_id ON calls(deal_id);
CREATE INDEX idx_calls_fecha ON calls(fecha);
CREATE INDEX idx_calls_crm_id ON calls(crm_id);
CREATE INDEX idx_calls_hs_deal_id ON calls(hs_deal_id);
CREATE INDEX idx_calls_owner_email ON calls(owner_email);
CREATE INDEX idx_calls_rol ON calls(rol);

CREATE INDEX idx_pbd_audits_call_id ON pbd_audits(call_id);
CREATE INDEX idx_pbd_audits_deal_ref ON pbd_audits(deal_ref);

CREATE INDEX idx_pae_audits_call_id ON pae_audits(call_id);
CREATE INDEX idx_pae_audits_deal_ref ON pae_audits(deal_ref);

CREATE INDEX idx_emails_deal_id ON emails(deal_id);
CREATE INDEX idx_emails_company_id ON emails(company_id);
CREATE INDEX idx_emails_hs_deal_id ON emails(hs_deal_id);
CREATE INDEX idx_emails_date ON emails(date);
CREATE INDEX idx_emails_crm_id ON emails(crm_id);

CREATE INDEX idx_company_atlas_crm_id ON company_atlas(crm_id);

CREATE INDEX idx_deal_confirmations_all_ready
    ON deal_confirmations(all_ready)
    WHERE all_ready = true;

CREATE INDEX idx_front_deal_snapshots_deal ON front_deal_snapshots(hs_deal_id, snapshot_date);
CREATE INDEX idx_front_deal_snapshots_date ON front_deal_snapshots(snapshot_date);

CREATE INDEX idx_front_rep_snapshots_email ON front_rep_snapshots(rep_email, snapshot_date);
CREATE INDEX idx_front_rep_aggregates_email ON front_rep_aggregates(rep_email);
CREATE INDEX idx_front_rep_briefs_email ON front_rep_briefs(rep_email);


-- ============================================================================
-- Auto-update updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_deals_updated_at BEFORE UPDATE ON deals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_calls_updated_at BEFORE UPDATE ON calls
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_pbd_audits_updated_at BEFORE UPDATE ON pbd_audits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_pae_audits_updated_at BEFORE UPDATE ON pae_audits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_emails_updated_at BEFORE UPDATE ON emails
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_company_atlas_updated_at BEFORE UPDATE ON company_atlas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_deal_confirmations_updated_at BEFORE UPDATE ON deal_confirmations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_front_deal_snapshots_updated_at BEFORE UPDATE ON front_deal_snapshots
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_front_rep_snapshots_updated_at BEFORE UPDATE ON front_rep_snapshots
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_front_rep_aggregates_updated_at BEFORE UPDATE ON front_rep_aggregates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_front_rep_briefs_updated_at BEFORE UPDATE ON front_rep_briefs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================================================
-- Row Level Security
-- ============================================================================

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE pbd_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE pae_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_atlas ENABLE ROW LEVEL SECURITY;
ALTER TABLE config ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_confirmations ENABLE ROW LEVEL SECURITY;
ALTER TABLE front_deal_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE front_rep_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE front_rep_aggregates ENABLE ROW LEVEL SECURITY;
ALTER TABLE front_rep_briefs ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS. These policies allow authenticated frontend reads.
CREATE POLICY "Authenticated read" ON companies FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON deals FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON calls FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON pbd_audits FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON pae_audits FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON emails FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON company_atlas FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON deal_confirmations FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON front_deal_snapshots FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON front_rep_snapshots FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON front_rep_aggregates FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated read" ON front_rep_briefs FOR SELECT TO authenticated USING (true);
