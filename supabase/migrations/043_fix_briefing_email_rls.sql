-- ============================================================================
-- Migration 043: Add authenticated RLS policies to briefings + email_drafts
-- ============================================================================
-- Both tables had RLS enabled but only anon + service_role policies.
-- The UI authenticates users → role = authenticated → got 0 rows.
-- ============================================================================

CREATE POLICY IF NOT EXISTS "Authenticated read"
  ON briefings FOR SELECT TO authenticated USING (true);

CREATE POLICY IF NOT EXISTS "Authenticated insert"
  ON briefings FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Authenticated read"
  ON email_drafts FOR SELECT TO authenticated USING (true);

CREATE POLICY IF NOT EXISTS "Authenticated insert"
  ON email_drafts FOR INSERT TO authenticated WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Authenticated update"
  ON email_drafts FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
