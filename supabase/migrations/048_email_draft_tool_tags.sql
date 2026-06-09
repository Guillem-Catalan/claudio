-- ============================================================================
-- Migration 048: Email draft trigger detects next_step tool tags
-- ============================================================================
-- Add [email], [battlecard], [roi], [slides] tag detection to the
-- auto_email_draft_after_snapshot trigger. These tags come from the
-- new next_step format in output_spec.
-- ============================================================================

CREATE OR REPLACE FUNCTION auto_email_draft_after_snapshot()
RETURNS TRIGGER AS $$
DECLARE
  _should_draft BOOLEAN := FALSE;
  _next_step TEXT;
  _deal_context_len INTEGER;
BEGIN
  -- ── Reason 1: action_signal contains email-related keywords ──
  SELECT EXISTS (
    SELECT 1
    WHERE LOWER(COALESCE(NEW.action_signal, ''))
      SIMILAR TO '%(email|correo|enviar|escribir|mandar|send)%'
  ) INTO _should_draft;

  -- ── Reason 2: next_step recommends sending an email or uses tool tags ──
  IF NOT _should_draft THEN
    _next_step := LOWER(COALESCE(NEW.next_step, ''));
    IF _next_step LIKE '%[email]%'
       OR _next_step LIKE '%[battlecard]%'
       OR _next_step LIKE '%[roi]%'
       OR _next_step LIKE '%[slides]%'
       OR _next_step LIKE '%enviar email%'
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

  -- ── Check deal_context length ──
  SELECT LENGTH(COALESCE(d.deal_context, ''))
  INTO _deal_context_len
  FROM deals d
  WHERE d.id = NEW.deal_id;

  IF _deal_context_len IS NULL OR _deal_context_len < 500 THEN
    RETURN NEW;
  END IF;

  -- ── Insert draft request ──
  INSERT INTO email_drafts (deal_id, deal_name, status, context_length)
  VALUES (NEW.deal_id, NEW.deal_name, 'pending', _deal_context_len)
  ON CONFLICT (deal_id) DO NOTHING;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
