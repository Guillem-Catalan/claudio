-- Migration 038: Fix missing RLS policies on front_deal_snapshots
--
-- The table was created by migration 008 (not 001), which didn't include
-- RLS policies. Only an "Anon read" policy existed (added manually),
-- so authenticated users got 0 rows — breaking the entire UI.

CREATE POLICY IF NOT EXISTS "Authenticated read"
  ON front_deal_snapshots FOR SELECT TO authenticated USING (true);

CREATE POLICY IF NOT EXISTS "Service role full access"
  ON front_deal_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);
