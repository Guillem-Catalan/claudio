-- ============================================================================
-- Migration 008: Create front_deal_snapshots table
-- ============================================================================
--
-- Table was defined in 001_initial_schema.sql but not applied to the database.
-- Creates it now so front_deals.yml can write snapshots.
-- ============================================================================

CREATE TABLE IF NOT EXISTS front_deal_snapshots (
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

CREATE INDEX IF NOT EXISTS idx_front_deals_deal_id
    ON front_deal_snapshots(deal_id);

CREATE INDEX IF NOT EXISTS idx_front_deals_snapshot
    ON front_deal_snapshots(hs_deal_id, snapshot_date);
