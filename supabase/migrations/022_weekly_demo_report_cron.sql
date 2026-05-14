-- ============================================================================
-- 022: Weekly Demo Report — replace per-INSERT trigger with Monday cron
-- ============================================================================

-- Drop old per-INSERT trigger and function
DROP TRIGGER IF EXISTS trg_demo_report ON audit_demos;
DROP FUNCTION IF EXISTS dispatch_demo_report();

-- ── Single weekly dispatch — Python iterates PAEs internally ────────────

CREATE OR REPLACE FUNCTION dispatch_weekly_demo_report()
RETURNS void AS $$
DECLARE github_pat TEXT;
BEGIN
  SELECT decrypted_secret INTO github_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat'
  LIMIT 1;

  IF github_pat IS NULL THEN
    RAISE WARNING 'github_pat not found in vault';
    RETURN;
  END IF;

  PERFORM net.http_post(
    url := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/demo_report.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || github_pat,
      'Accept', 'application/vnd.github.v3+json',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object('ref', 'main')
  );
END;
$$ LANGUAGE plpgsql;

SELECT cron.schedule(
  'weekly_demo_report',
  '0 7 * * 1',
  'SELECT dispatch_weekly_demo_report()'
);
