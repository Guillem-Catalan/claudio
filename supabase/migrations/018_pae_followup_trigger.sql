-- Trigger: mark pae_followup_pending when a PAE Demo call is audited.
-- Fires when win_rate_score transitions from NULL to NOT NULL
-- and the associated call has tag 'Partners - PAE Demo'.
-- Does NOT dispatch the workflow directly — the follow-up fires
-- after front_deal_snapshots is generated (see migration 019).

-- Add the pending flag to deal_confirmations
ALTER TABLE deal_confirmations
    ADD COLUMN IF NOT EXISTS pae_followup_pending BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS pae_followup_call_ref UUID;

CREATE OR REPLACE FUNCTION mark_pae_followup_pending()
RETURNS TRIGGER AS $$
DECLARE
    _tags TEXT[];
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
    SET pae_followup_pending = TRUE,
        pae_followup_call_ref = NEW.call_ref,
        updated_at = NOW()
    WHERE deal_id = _deal_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pae_followup ON pae_audits;

CREATE TRIGGER trg_pae_followup
    AFTER UPDATE ON pae_audits
    FOR EACH ROW
    WHEN (OLD.win_rate_score IS NULL AND NEW.win_rate_score IS NOT NULL)
    EXECUTE FUNCTION mark_pae_followup_pending();
