-- ============================================================================
-- Migration 051: Don't mark closed deals as context_stale
-- ============================================================================
-- The trigger was firing for all deals, including closed ones.
-- Closed deals don't need snapshots, so skip them.
-- ============================================================================

CREATE OR REPLACE FUNCTION mark_context_stale()
RETURNS TRIGGER AS $$
BEGIN
  -- Skip closed stages
  IF NEW.deal_stage IN (
    'Closed Won', 'Closed Lost', 'Closed won', 'Closed lost',
    'Opportunity lost', 'Opportunity Lost',
    'Closed Won - Finance Only', 'Closed - pending finance validation',
    'Closed Pending Payment',
    'Onboarding Completed - Converted', 'Onboarding Completed - Pending Conversion',
    'Onboarding Failed', 'Onboarding On Hold',
    'Churned (Closed)', 'Retained (Closed)',
    'Wrongly Created Ticket (Closed)', 'SPAM',
    'Preventive Churn Risk (New)', 'Requested Churn (New)',
    '(DO NOT USE) Churn Confirmed',
    'Product related process (Ongoing)',
    'Pending approval because low joined rate',
    '(DO NOT USE) Pending Post-Mortem Analysis',
    '(DO NOT USE) Action Plan',
    '> 75% sessions done', '51-75% sessions done',
    '26-50% sessions done', '≤ 25% sessions done',
    '1st Session Scheduled', 'Client pending to launch',
    'Opportunity Lost '
  ) THEN
    RETURN NEW;
  END IF;

  IF (OLD.numero_de_emails IS DISTINCT FROM NEW.numero_de_emails
      OR OLD.numero_de_notas IS DISTINCT FROM NEW.numero_de_notas
      OR OLD.numero_de_calls IS DISTINCT FROM NEW.numero_de_calls
      OR OLD.numero_de_meetings IS DISTINCT FROM NEW.numero_de_meetings)
  THEN
    NEW.context_stale := TRUE;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
