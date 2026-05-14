-- ============================================================================
-- 024: Webhook POST to frontend after demo snapshot is generated
-- ============================================================================
-- Pattern: same as 018 + 020 (flag in deal_confirmations, read after snapshot)
--
-- Flow:
--   1. pae_audits UPDATE (win_rate_score NULL → NOT NULL, demo tag)
--      → mark_demo_webhook_pending() sets flag + call_ref
--   2. front_deal_snapshots INSERT
--      → dispatch_demo_webhook() reads flag, POSTs to edge function, clears flag

-- ── Step 1: Add columns to deal_confirmations ───────────────────────────────

ALTER TABLE deal_confirmations
    ADD COLUMN IF NOT EXISTS demo_webhook_pending BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS demo_webhook_call_ref UUID;

-- ── Step 2: Mark flag when a PAE Demo is audited ────────────────────────────

CREATE OR REPLACE FUNCTION mark_demo_webhook_pending()
RETURNS TRIGGER AS $$
DECLARE
    _tags    TEXT[];
    _deal_id UUID;
BEGIN
    SELECT tags, deal_id INTO _tags, _deal_id
    FROM calls
    WHERE id = NEW.call_ref;

    IF _tags IS NULL OR NOT ('Partners - PAE Demo' = ANY(_tags)) THEN
        RETURN NEW;
    END IF;

    IF _deal_id IS NULL THEN
        RETURN NEW;
    END IF;

    UPDATE deal_confirmations
    SET demo_webhook_pending = TRUE,
        demo_webhook_call_ref = NEW.call_ref,
        updated_at = NOW()
    WHERE deal_id = _deal_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_demo_webhook_flag ON pae_audits;

CREATE TRIGGER trg_demo_webhook_flag
    AFTER INSERT OR UPDATE ON pae_audits
    FOR EACH ROW
    WHEN (NEW.win_rate_score IS NOT NULL)
    EXECUTE FUNCTION mark_demo_webhook_pending();

-- ── Step 3: POST webhook after front_deal_snapshots INSERT ──────────────────

CREATE OR REPLACE FUNCTION dispatch_demo_webhook()
RETURNS TRIGGER AS $$
DECLARE
    _call_ref  UUID;
    _call      RECORD;
    _deal      RECORD;
    _api_key   TEXT;
    _payload   JSONB;
    _company   TEXT;
BEGIN
    -- Check if there is a pending demo webhook for this deal
    SELECT demo_webhook_call_ref INTO _call_ref
    FROM deal_confirmations
    WHERE deal_id = NEW.deal_id
      AND demo_webhook_pending = TRUE;

    IF _call_ref IS NULL THEN
        RETURN NEW;
    END IF;

    -- Clear the flag before dispatching
    UPDATE deal_confirmations
    SET demo_webhook_pending = FALSE,
        updated_at = NOW()
    WHERE deal_id = NEW.deal_id;

    -- Fetch call data (transcript, owner)
    SELECT * INTO _call FROM calls WHERE id = _call_ref;
    IF _call IS NULL THEN
        RETURN NEW;
    END IF;

    -- Fetch deal data
    SELECT * INTO _deal FROM deals WHERE id = NEW.deal_id;
    IF _deal IS NULL THEN
        RETURN NEW;
    END IF;

    -- Strip " - from <Partner>" suffix from deal_name for company_name
    _company := regexp_replace(
        COALESCE(_deal.deal_name, ''),
        '\s*-\s*from\s+\w+$', '', 'i'
    );

    -- Get API key from vault
    SELECT decrypted_secret INTO _api_key
    FROM vault.decrypted_secrets
    WHERE name = 'front_webhook_api_key';

    IF _api_key IS NULL THEN
        RAISE WARNING 'front_webhook_api_key not found in vault';
        RETURN NEW;
    END IF;

    -- Build payload
    _payload := jsonb_build_object(
        'titulo',                COALESCE(_call.owner_nombre, ''),
        'owner_email',           COALESCE(_call.owner_email, ''),
        'rol',                   'PAE',
        'company_name',          _company,
        'transcript',            COALESCE(_call.transcript, ''),
        'presentation_use_case', 'post_demo',
        'front_deals', jsonb_build_object(
            'deal_summary',   COALESCE(NEW.deal_summary, ''),
            'm_accumulate',   COALESCE(NEW.m_accumulate, ''),
            'e_accumulate',   COALESCE(NEW.e_accumulate, ''),
            'dc_accumulate',  COALESCE(NEW.dc_accumulate, ''),
            'dp_accumulate',  COALESCE(NEW.dp_accumulate, ''),
            'i_accumulate',   COALESCE(NEW.i_accumulate, ''),
            'c_accumulate',   COALESCE(NEW.c_accumulate, ''),
            'objections',     COALESCE(NEW.objections, ''),
            'buyer_signals',  COALESCE(NEW.buyer_signals, ''),
            'live_blockers',  COALESCE(NEW.live_blockers, ''),
            'deal_strengths', COALESCE(NEW.deal_strengths, '')
        ),
        'deal_data', jsonb_build_object(
            'hs_deal_id',        COALESCE(_deal.deal_id, ''),
            'stage',             COALESCE(_deal.deal_stage, ''),
            'amount',            COALESCE(_deal.amount, 0),
            'forecast_category', COALESCE(_deal.forecast_category, ''),
            'close_date',        COALESCE(_deal.close_date::text, ''),
            'deal_age_days',     COALESCE(_deal.deal_age_days, 0),
            'pbd',               COALESCE(_deal.pbd, ''),
            'pae',               COALESCE(_deal.pae, '')
        )
    );

    -- POST to frontend webhook
    PERFORM net.http_post(
        url     := 'https://zuvqncurnxkocmmcvdkk.supabase.co/functions/v1/webhook-front-deal',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'x-api-key', _api_key
        ),
        body    := _payload
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_demo_webhook_after_snapshot ON front_deal_snapshots;

CREATE TRIGGER trg_demo_webhook_after_snapshot
    AFTER INSERT ON front_deal_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_demo_webhook();
