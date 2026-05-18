-- 025: Adapt to HubSpot Partners Distribution pipeline changes (2026-05-18)
--
-- Stage renames:
--   Product Alignment → Factorial Project Alignment started
--   Pricing & Packaging → Economical Allignment Started
--   Contracting → Contract Sent
--   Closed Pending Payment → Closed - pending finance validation
--
-- New stage:
--   MEDDPICC Criteria Validation Started (id: 5366023400)

-- New date columns for MEDDPICC stage
ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS dist_meddpicc_validation_entered DATE,
  ADD COLUMN IF NOT EXISTS dist_meddpicc_validation_exited DATE;

-- Update EB alert trigger to match all 3 variants of the pricing stage
CREATE OR REPLACE FUNCTION dispatch_eb_alert()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    _pat TEXT;
BEGIN
    IF OLD.deal_stage IS NOT DISTINCT FROM NEW.deal_stage THEN
        RETURN NEW;
    END IF;

    IF NEW.deal_stage NOT IN (
        'Pricing and Packaging',
        'Pricing & Packaging',
        'Economical Allignment Started'
    ) THEN
        RETURN NEW;
    END IF;

    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets
    WHERE name = 'github_pat';

    PERFORM net.http_post(
        url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/eb_alert.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github.v3+json',
            'Content-Type', 'application/json'
        ),
        body := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'deal_uuid', NEW.id::TEXT,
                'deal_id', NEW.deal_id
            )
        )
    );

    RETURN NEW;
END;
$$;
