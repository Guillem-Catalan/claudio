-- Fix dispatch_pae_demo_prep to use correct demo detection logic:
-- deal_stage = Demo Booked + first_meeting_at = tomorrow + not yet done + has PAE

CREATE OR REPLACE FUNCTION dispatch_pae_demo_prep()
RETURNS void AS $$
DECLARE
  tomorrow DATE := CURRENT_DATE + INTERVAL '1 day';
  deal RECORD;
  github_pat TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  FOR deal IN
    SELECT id::TEXT AS deal_uuid
    FROM deals
    WHERE deal_stage = 'Demo Booked'
      AND first_meeting_at = tomorrow
      AND (dist_demo_booked_exited IS NULL OR dist_demo_booked_exited < dist_demo_booked_entered)
      AND pae IS NOT NULL
      AND pae != ''
  LOOP
    PERFORM net.http_post(
      url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/pae_demo_prep.yml/dispatches',
      headers := jsonb_build_object(
        'Authorization', 'Bearer ' || github_pat,
        'Accept', 'application/vnd.github.v3+json',
        'Content-Type', 'application/json'
      ),
      body := jsonb_build_object(
        'ref', 'main',
        'inputs', jsonb_build_object('deal_uuid', deal.deal_uuid)
      )
    );
    RAISE NOTICE 'Dispatched pae_demo_prep for deal %', deal.deal_uuid;
  END LOOP;
END;
$$ LANGUAGE plpgsql;
