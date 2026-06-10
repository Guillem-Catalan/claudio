-- =====================================================================
-- v_deals_dashboard
-- Contrato único front ↔ back para la pestaña Deals.
-- Una fila por deal activo. Los alias son el contrato — el back puede
-- renombrar columnas reales y solo se actualiza la cláusula SELECT aquí.
--
-- Ejecutar en el SQL editor del proyecto Supabase bqoepgcdgqylobkmqdur.
-- Idempotente: CREATE OR REPLACE VIEW.
-- =====================================================================

CREATE OR REPLACE VIEW public.v_deals_dashboard AS
WITH
-- Último snapshot por deal
latest_snap AS (
  SELECT DISTINCT ON (deal_id) *
  FROM public.front_deal_snapshots
  ORDER BY deal_id, snapshot_date DESC
),
-- Snapshot anterior para calcular tendencia
prev_snap AS (
  SELECT deal_id, close_probability AS prev_prob
  FROM (
    SELECT
      deal_id,
      close_probability,
      snapshot_date,
      ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY snapshot_date DESC) AS rn
    FROM public.front_deal_snapshots
  ) s
  WHERE rn = 2
),
-- Último PBD snapshot por deal
latest_pbd AS (
  SELECT DISTINCT ON (deal_id)
    deal_id,
    bant_b_status, bant_a_status, bant_n_status, bant_t_status,
    snapshot_date AS pbd_snapshot_date
  FROM public.pbd_snapshots
  ORDER BY deal_id, snapshot_date DESC
),
-- Meeting más relevante de hoy (el último por deal)
meet_today AS (
  SELECT DISTINCT ON (deal_id)
    deal_id,
    meeting_start AS meeting_today_at,
    outcome       AS meeting_today_outcome,
    title         AS meeting_today_title
  FROM public.deal_meetings
  WHERE meeting_start::date = CURRENT_DATE
  ORDER BY deal_id, meeting_start DESC
),
-- Meeting de ayer (el último por deal)
meet_yesterday AS (
  SELECT DISTINCT ON (deal_id)
    deal_id,
    meeting_start AS meeting_yesterday_at,
    outcome       AS meeting_yesterday_outcome,
    title         AS meeting_yesterday_title
  FROM public.deal_meetings
  WHERE meeting_start::date = CURRENT_DATE - INTERVAL '1 day'
  ORDER BY deal_id, meeting_start DESC
),
-- Mapeo stage → phase (debe coincidir con PIPELINE_PHASES del front)
stage_phase(stage, phase, stale_days) AS (
  VALUES
    -- closing
    ('Economical Allignment Started','closing',7),
    ('Economical Alignment Started','closing',7),
    ('Pricing and Packaging','closing',7),
    ('Pricing & Packaging','closing',7),
    ('Contract Sent','closing',7),
    -- evaluating
    ('Factorial Project Alignment started','evaluating',10),
    ('MEDDPICC Criteria Validation Started','evaluating',10),
    ('Product Alignment','evaluating',10),
    -- demo
    ('Demo Booked','demo',7),
    ('Meeting Booked','demo',7),
    ('Meeting scheduled','demo',7),
    ('Discovery','demo',7),
    -- nurturing
    ('Nurturing','nurturing',21),
    ('Sales Nurturing','nurturing',21),
    ('Hot Nurturing','nurturing',21),
    ('Long Nurturing','nurturing',21),
    ('To reschedule','nurturing',21),
    -- qualifying
    ('Attempting to contact','qualifying',10),
    ('Attempted to contact','qualifying',10),
    ('Client Contacted','qualifying',10),
    ('Connected - Not Engaged','qualifying',10),
    ('Engaged','qualifying',10),
    ('Pre-qualified','qualifying',10),
    -- prospecting
    ('New','prospecting',14),
    ('New Deals','prospecting',14),
    ('Research & Outreach','prospecting',14),
    ('Associating the partner','prospecting',14),
    ('Opportunity detected','prospecting',14),
    -- onhold
    ('On Hold','onhold',30)
)
SELECT
  -- Identidad
  d.id                                                AS deal_id,
  d.deal_id                                           AS hs_deal_id,
  d.deal_name                                         AS deal_name,
  d.deal_stage                                        AS deal_stage,
  COALESCE(sp.phase, 'other')                         AS phase,
  d.amount                                            AS amount,
  d.close_date                                        AS close_date,
  d.deal_age_days                                     AS deal_age_days,
  COALESCE(d.pae, d.pbd)                              AS owner,
  d.pae                                               AS pae,
  d.pbd                                               AS pbd,
  d.forecast_category                                 AS forecast_category,
  d.atlas_id                                          AS atlas_id,
  d.rep_next_step                                     AS rep_next_step,
  d.first_meeting_at                                  AS first_meeting_at,
  d.createdate                                        AS created_at,

  -- Contacto / staleness
  d.last_contacted_hs                                 AS last_contacted_hs,
  CASE
    WHEN d.last_contacted_hs IS NULL THEN NULL
    ELSE EXTRACT(DAY FROM (now() - d.last_contacted_hs))::int
  END                                                 AS days_since_contact,
  CASE
    WHEN d.last_contacted_hs IS NULL THEN false
    ELSE EXTRACT(DAY FROM (now() - d.last_contacted_hs))
         > COALESCE(sp.stale_days, 14)
  END                                                 AS is_stale,

  -- Snapshot meta
  s.snapshot_date                                     AS snapshot_date,

  -- MEDDICC
  s.m_score                                           AS m_score,
  s.e_score                                           AS e_score,
  s.dc_score                                          AS dc_score,
  s.dp_score                                          AS dp_score,
  s.i_score                                           AS i_score,
  s.c_score                                           AS c_score,
  s.comp_score                                        AS comp_score,
  (
    (COALESCE(s.m_score,0) + COALESCE(s.e_score,0) + COALESCE(s.dc_score,0)
   + COALESCE(s.dp_score,0) + COALESCE(s.i_score,0) + COALESCE(s.c_score,0)
   + COALESCE(s.comp_score,0))::numeric
    / NULLIF(
        (CASE WHEN s.m_score IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN s.e_score IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN s.dc_score IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN s.dp_score IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN s.i_score IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN s.c_score IS NOT NULL THEN 1 ELSE 0 END
       + CASE WHEN s.comp_score IS NOT NULL THEN 1 ELSE 0 END), 0)
  )                                                   AS meddicc_avg,

  -- Forecast / probabilidad
  s.close_probability                                 AS close_probability,
  s.claudio_forecast                                  AS claudio_forecast,
  CASE
    WHEN ps.prev_prob IS NULL OR s.close_probability IS NULL THEN 'flat'
    WHEN s.close_probability > ps.prev_prob THEN 'up'
    WHEN s.close_probability < ps.prev_prob THEN 'down'
    ELSE 'flat'
  END                                                 AS prob_trend,

  -- Señales / contenido
  s.action_signal                                     AS action_signal,
  s.live_blockers                                     AS live_blockers,
  s.next_step                                         AS next_step,
  s.buyer_signals                                     AS buyer_signals,
  s.deal_strengths                                    AS deal_strengths,
  s.improvements                                      AS improvements,
  s.objections                                        AS objections,
  s.deal_summary                                      AS deal_summary,
  s.deal_assessment                                   AS deal_assessment,

  -- Señal derivada (jerarquía: stale > blocker > action > next > buyer)
  CASE
    WHEN d.last_contacted_hs IS NOT NULL
     AND EXTRACT(DAY FROM (now() - d.last_contacted_hs)) > COALESCE(sp.stale_days, 14)
      THEN 'stale'
    WHEN COALESCE(s.live_blockers, '') <> '' THEN 'blocker'
    WHEN COALESCE(s.action_signal, '') <> '' THEN 'action'
    WHEN COALESCE(s.next_step, '')     <> '' THEN 'next'
    WHEN COALESCE(s.buyer_signals, '') <> '' THEN 'buyer'
    ELSE 'idle'
  END                                                 AS signal_kind,

  -- BANT (último PBD)
  lp.bant_b_status                                    AS bant_b_status,
  lp.bant_a_status                                    AS bant_a_status,
  lp.bant_n_status                                    AS bant_n_status,
  lp.bant_t_status                                    AS bant_t_status,
  (
    (CASE WHEN lp.bant_b_status = 'confirmed' THEN 1 ELSE 0 END)
  + (CASE WHEN lp.bant_a_status = 'confirmed' THEN 1 ELSE 0 END)
  + (CASE WHEN lp.bant_n_status = 'confirmed' THEN 1 ELSE 0 END)
  + (CASE WHEN lp.bant_t_status = 'confirmed' THEN 1 ELSE 0 END)
  )                                                   AS bant_confirmed_count,

  -- Meetings hoy / ayer
  mt.meeting_today_at                                 AS meeting_today_at,
  mt.meeting_today_outcome                            AS meeting_today_outcome,
  mt.meeting_today_title                              AS meeting_today_title,
  my.meeting_yesterday_at                             AS meeting_yesterday_at,
  my.meeting_yesterday_outcome                        AS meeting_yesterday_outcome,
  my.meeting_yesterday_title                          AS meeting_yesterday_title,
  CASE
    WHEN mt.meeting_today_at IS NOT NULL     THEN 'today'
    WHEN my.meeting_yesterday_at IS NOT NULL THEN 'yesterday'
    ELSE 'none'
  END                                                 AS today_bucket

FROM public.deals d
LEFT JOIN stage_phase    sp ON sp.stage = d.deal_stage
LEFT JOIN latest_snap    s  ON s.deal_id  = d.id
LEFT JOIN prev_snap      ps ON ps.deal_id = d.id
LEFT JOIN latest_pbd     lp ON lp.deal_id = d.id
LEFT JOIN meet_today     mt ON mt.deal_id = d.id
LEFT JOIN meet_yesterday my ON my.deal_id = d.id
WHERE d.deal_stage NOT IN (
  'Opportunity lost','Closed lost','Closed Lost','Closed won','Closed Won',
  'Closed Won - Finance Only','Opportunity Lost','Opportunity Lost ',
  'Onboarding Completed - Converted','Onboarding Completed - Pending Conversion',
  'Onboarding Failed','Onboarding On Hold',
  '> 75% sessions done','51-75% sessions done','26-50% sessions done',
  '≤ 25% sessions done','1st Session Scheduled','Client pending to launch',
  'Churned (Closed)','Retained (Closed)','Preventive Churn Risk (New)',
  'Requested Churn (New)','(DO NOT USE) Churn Confirmed',
  'Product related process (Ongoing)','Pending approval because low joined rate',
  'Wrongly Created Ticket (Closed)','SPAM',
  '(DO NOT USE) Pending Post-Mortem Analysis','(DO NOT USE) Action Plan',
  'Closed - pending finance validation'
)
AND COALESCE(d.deal_name, '') NOT ILIKE '%session%';

-- Lectura para clientes autenticados y anónimos (el front usa anon key).
GRANT SELECT ON public.v_deals_dashboard TO authenticated, anon;
