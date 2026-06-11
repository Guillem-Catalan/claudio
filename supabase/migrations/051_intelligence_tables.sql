-- ============================================================================
-- Migration 051: Intelligence layer — Claudio's learning core
-- ============================================================================
-- deal_trajectories: complete history of every closed deal (auto-populated)
-- learned_patterns: patterns extracted from trajectories (generated weekly)
-- calibration_log: forecast accuracy tracking (generated monthly)
-- New columns on front_deal_snapshots for forecast v2
-- New column on deals for closed_lost_reason
-- ============================================================================

-- ── 1. closed_lost_reason on deals ──────────────────────────────────────

ALTER TABLE deals ADD COLUMN IF NOT EXISTS closed_lost_reason TEXT;

-- ── 2. Forecast v2 columns on front_deal_snapshots ──────────────────────

ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS closes_this_month BOOLEAN;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS closes_next_month BOOLEAN;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS forecast_confidence TEXT;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS forecast_reasoning TEXT;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS forecast_risks TEXT;
ALTER TABLE front_deal_snapshots ADD COLUMN IF NOT EXISTS forecast_accelerators TEXT;

-- ── 3. deal_trajectories ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS deal_trajectories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_id UUID REFERENCES deals(id),
  outcome TEXT NOT NULL CHECK (outcome IN ('won', 'lost', 'on_hold')),
  amount NUMERIC,
  deal_age_days INTEGER,
  pae TEXT,
  pbd TEXT,
  team TEXT,
  pipeline_name TEXT,
  closed_lost_reason TEXT,
  close_date DATE,

  trajectory JSONB NOT NULL,
  stage_dates JSONB,
  interactions JSONB,
  lessons JSONB,

  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trajectories_outcome ON deal_trajectories(outcome);
CREATE INDEX IF NOT EXISTS idx_trajectories_team ON deal_trajectories(team);
CREATE INDEX IF NOT EXISTS idx_trajectories_amount ON deal_trajectories(amount);

ALTER TABLE deal_trajectories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON deal_trajectories FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON deal_trajectories FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service all" ON deal_trajectories FOR ALL TO service_role USING (true);

-- ── 4. learned_patterns ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS learned_patterns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_type TEXT NOT NULL,
  scope TEXT,
  pattern TEXT NOT NULL,
  confidence NUMERIC,
  sample_size INTEGER,
  generated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE learned_patterns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON learned_patterns FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON learned_patterns FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service all" ON learned_patterns FOR ALL TO service_role USING (true);

-- ── 5. calibration_log ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS calibration_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  month TEXT NOT NULL,
  deal_id UUID REFERENCES deals(id),
  deal_name TEXT,
  predicted_close_this_month BOOLEAN,
  predicted_confidence TEXT,
  actual_outcome TEXT,
  error_analysis TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE calibration_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON calibration_log FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON calibration_log FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service all" ON calibration_log FOR ALL TO service_role USING (true);
