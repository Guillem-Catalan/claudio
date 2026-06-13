-- ============================================================================
-- Migration 053: model_migration_tests table for A/B testing models
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_migration_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_id UUID,
  deal_name TEXT,
  task TEXT NOT NULL,
  model TEXT NOT NULL,
  output JSONB,
  output_text TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  duration_ms INTEGER,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mmt_task_model ON model_migration_tests(task, model);
ALTER TABLE model_migration_tests ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service all" ON model_migration_tests FOR ALL TO service_role USING (true);
CREATE POLICY "Anon read" ON model_migration_tests FOR SELECT TO anon USING (true);
