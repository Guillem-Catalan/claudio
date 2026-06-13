-- ============================================================================
-- Migration 055: deal_actions — single source of truth for rep actions
-- ============================================================================

CREATE TABLE IF NOT EXISTS deal_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  snapshot_date DATE,

  -- Unified action (synthesized from action_signal + push_action + next_step + accelerators)
  action_headline TEXT NOT NULL,
  action_detail TEXT,
  action_type TEXT,
  action_who TEXT,
  action_when TEXT,
  action_priority INT DEFAULT 3,

  -- Follow-up timeline
  follow_ups JSONB DEFAULT '[]'::jsonb,

  -- Context for display
  deal_name TEXT,
  deal_owner TEXT,
  deal_mrr NUMERIC,
  deal_stage TEXT,
  bucket TEXT,
  claudio_close_date TEXT,

  -- Tracking
  status TEXT DEFAULT 'pending',
  completed_at TIMESTAMPTZ,
  completed_by TEXT,

  -- Learning
  deal_advanced BOOLEAN,
  previous_action_id UUID,

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(deal_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_deal_actions_deal_id ON deal_actions(deal_id);
CREATE INDEX IF NOT EXISTS idx_deal_actions_status ON deal_actions(status);
CREATE INDEX IF NOT EXISTS idx_deal_actions_owner ON deal_actions(deal_owner);
CREATE INDEX IF NOT EXISTS idx_deal_actions_bucket ON deal_actions(bucket);

-- RLS: allow anon read, service_role write
ALTER TABLE deal_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_deal_actions" ON deal_actions FOR SELECT USING (true);
CREATE POLICY "service_write_deal_actions" ON deal_actions FOR ALL USING (true) WITH CHECK (true);
