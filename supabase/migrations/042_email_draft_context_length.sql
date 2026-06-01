-- ============================================================================
-- Migration 042: Use deal_context length instead of updated_at for dedup
-- ============================================================================
-- deals.updated_at gets bumped by every hourly sync_deals upsert, making it
-- useless as a "new activity" signal. Instead, store the length of
-- deal_context when the email is generated. If context grew (new calls,
-- emails, meetings), there's real new activity → generate new email.
-- ============================================================================

ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS context_length INTEGER;

-- Update trigger to use context_length comparison
CREATE OR REPLACE FUNCTION auto_email_draft_after_snapshot()
RETURNS TRIGGER AS $$
DECLARE
  _deal_uuid UUID;
  _should_draft BOOLEAN := FALSE;
  _supa_url TEXT;
  _service_key TEXT;
  _next_step TEXT;
  _existing_status TEXT;
  _existing_context_length INTEGER;
  _current_context_length INTEGER;
BEGIN
  _deal_uuid := NEW.deal_id;
  IF _deal_uuid IS NULL THEN
    RETURN NEW;
  END IF;

  -- ── Reason 1: deal had a meeting today ──
  SELECT EXISTS (
    SELECT 1 FROM deal_meetings
    WHERE deal_id = _deal_uuid
      AND meeting_start::date = CURRENT_DATE
    UNION ALL
    SELECT 1 FROM calendar_meetings
    WHERE deal_id = _deal_uuid
      AND resolved = true
      AND meeting_start::date = CURRENT_DATE
  ) INTO _should_draft;

  -- ── Reason 2: next_step recommends sending an email ──
  IF NOT _should_draft THEN
    _next_step := LOWER(COALESCE(NEW.next_step, ''));
    IF _next_step LIKE '%enviar email%'
       OR _next_step LIKE '%enviar correo%'
       OR _next_step LIKE '%enviar un email%'
       OR _next_step LIKE '%enviar un correo%'
       OR _next_step LIKE '%escribir a%'
       OR _next_step LIKE '%escribir un email%'
       OR _next_step LIKE '%mandar email%'
       OR _next_step LIKE '%mandar correo%'
       OR _next_step LIKE '%send email%'
       OR _next_step LIKE '%email a %'
       OR _next_step LIKE '%correo a %'
       OR _next_step LIKE '%enviar presupuesto%'
       OR _next_step LIKE '%enviar propuesta%'
       OR _next_step LIKE '%enviar resumen%'
       OR _next_step LIKE '%enviar recap%'
       OR _next_step LIKE '%enviar vídeo%'
       OR _next_step LIKE '%enviar video%'
       OR _next_step LIKE '%enviar documentación%'
       OR _next_step LIKE '%enviar info%'
       OR _next_step LIKE '% por email%'
       OR _next_step LIKE '% por correo%'
    THEN
      _should_draft := TRUE;
    END IF;
  END IF;

  IF NOT _should_draft THEN
    RETURN NEW;
  END IF;

  -- ── Timeline-aware dedup using deal_context length ──
  SELECT status, context_length
  INTO _existing_status, _existing_context_length
  FROM email_drafts
  WHERE deal_id = _deal_uuid
  ORDER BY created_at DESC
  LIMIT 1;

  IF _existing_status IS NOT NULL THEN
    -- Draft not sent yet → don't create another
    IF _existing_status = 'draft' THEN
      RETURN NEW;
    END IF;

    -- Sent (copied) → check if deal_context has grown since
    IF _existing_status = 'copied' AND _existing_context_length IS NOT NULL THEN
      SELECT COALESCE(LENGTH(deal_context), 0)
      INTO _current_context_length
      FROM deals
      WHERE id = _deal_uuid;

      IF _current_context_length <= _existing_context_length THEN
        -- Context hasn't grown → no new activity → wait for response
        RETURN NEW;
      END IF;
    END IF;
  END IF;

  -- ── Generate email draft ──
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
