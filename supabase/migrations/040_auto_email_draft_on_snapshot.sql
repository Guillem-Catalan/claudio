-- ============================================================================
-- Migration 040: Auto-generate email draft after snapshot for deals with
-- meetings today
-- ============================================================================
-- When a front_deal_snapshot is inserted, check if the deal had a meeting
-- today (in deal_meetings or calendar_meetings). If yes and no email_draft
-- exists for today, call the email-draft Edge Function to generate one.
-- ============================================================================

CREATE OR REPLACE FUNCTION auto_email_draft_after_snapshot()
RETURNS TRIGGER AS $$
DECLARE
  _deal_uuid UUID;
  _has_meeting BOOLEAN := FALSE;
  _has_draft BOOLEAN := FALSE;
  _supa_url TEXT;
  _service_key TEXT;
BEGIN
  _deal_uuid := NEW.deal_id;
  IF _deal_uuid IS NULL THEN
    RETURN NEW;
  END IF;

  -- Check if deal had a meeting today (deal_meetings or calendar_meetings)
  SELECT EXISTS (
    SELECT 1 FROM deal_meetings
    WHERE deal_id = _deal_uuid
      AND meeting_start::date = CURRENT_DATE
    UNION ALL
    SELECT 1 FROM calendar_meetings
    WHERE deal_id = _deal_uuid
      AND resolved = true
      AND meeting_start::date = CURRENT_DATE
  ) INTO _has_meeting;

  IF NOT _has_meeting THEN
    RETURN NEW;
  END IF;

  -- Check if there's already an email_draft for this deal today
  SELECT EXISTS (
    SELECT 1 FROM email_drafts
    WHERE deal_id = _deal_uuid
      AND created_at::date = CURRENT_DATE
  ) INTO _has_draft;

  IF _has_draft THEN
    RETURN NEW;
  END IF;

  -- Get service role key from vault
  SELECT decrypted_secret INTO _service_key
  FROM vault.decrypted_secrets
  WHERE name = 'service_role_key'
  LIMIT 1;

  IF _service_key IS NULL THEN
    RAISE WARNING 'service_role_key not found in vault';
    RETURN NEW;
  END IF;

  _supa_url := current_setting('app.settings.supabase_url', true);
  IF _supa_url IS NULL OR _supa_url = '' THEN
    _supa_url := 'https://bqoepgcdgqylobkmqdur.supabase.co';
  END IF;

  -- Call email-draft Edge Function
  PERFORM net.http_post(
    url     := _supa_url || '/functions/v1/email-draft',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || _service_key
    ),
    body    := jsonb_build_object('deal_id', _deal_uuid::text)
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_email_draft_after_snapshot
  AFTER INSERT ON front_deal_snapshots
  FOR EACH ROW
  EXECUTE FUNCTION auto_email_draft_after_snapshot();
