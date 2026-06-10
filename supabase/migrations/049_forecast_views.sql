-- ============================================================================
-- Migration 049: Forecast views + targets table
-- ============================================================================

-- ── forecast_targets: editable monthly targets per team ─────────────────
CREATE TABLE IF NOT EXISTS public.forecast_targets (
  team TEXT NOT NULL,
  month TEXT NOT NULL,
  monthly_target NUMERIC NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (team, month)
);

ALTER TABLE forecast_targets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read" ON forecast_targets FOR SELECT TO anon USING (true);
CREATE POLICY "Authenticated read" ON forecast_targets FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service all" ON forecast_targets FOR ALL TO service_role USING (true);

-- ── v_forecast_dashboard: validates forecast_category against deal_stage ──
CREATE OR REPLACE VIEW public.v_forecast_dashboard AS
SELECT d.*,
  CASE
    WHEN d.deal_stage IN ('On Hold','To reschedule','Attempting to contact',
         'Attempted to contact','Nurturing','Sales Nurturing','New','New Deals',
         'Connected - Not Engaged','Associating the partner')
      THEN 'Pipeline'
    WHEN d.close_date < CURRENT_DATE AND d.forecast_category = 'Commit'
      THEN 'Upside'
    WHEN d.close_date < CURRENT_DATE AND d.forecast_category IN ('Upside','Pipeline_new')
      THEN 'Pipeline'
    WHEN d.deal_stage IN ('Factorial Project Alignment started','Demo Booked',
         'Meeting Booked','Discovery','Product Alignment','Pre-qualified','Engaged')
         AND d.forecast_category = 'Commit'
      THEN 'Upside'
    ELSE COALESCE(d.forecast_category, 'Pipeline')
  END AS validated_forecast,
  CASE WHEN d.close_date < CURRENT_DATE THEN true ELSE false END AS close_date_passed
FROM public.v_deals_dashboard d
WHERE d.forecast_category IS NOT NULL AND d.forecast_category != '';

GRANT SELECT ON public.v_forecast_dashboard TO authenticated, anon;

-- ── v_deals_closed: closed won deals for "actual closed" tracking ────────
CREATE OR REPLACE VIEW public.v_deals_closed AS
SELECT d.id AS deal_id, d.deal_id AS hs_deal_id, d.deal_name, d.deal_stage,
       d.amount, d.close_date, d.pae, d.pbd, COALESCE(d.pae, d.pbd) AS owner
FROM public.deals d
WHERE d.deal_stage IN ('Closed Won','Closed won','Closed Won - Finance Only')
  AND COALESCE(d.deal_name, '') NOT ILIKE '%session%';

GRANT SELECT ON public.v_deals_closed TO authenticated, anon;
