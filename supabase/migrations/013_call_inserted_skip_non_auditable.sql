-- Only set calls_ready = FALSE when the inserted call is actually auditable.
-- Non-auditable calls (no role or short transcript) should not block the deal.

CREATE OR REPLACE FUNCTION dc_on_call_inserted()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.rol IS NOT NULL AND LENGTH(COALESCE(NEW.transcript, '')) >= 200 THEN
        UPDATE deal_confirmations
        SET calls_ready = FALSE,
            front_deal_triggered_at = NULL
        WHERE deal_id = NEW.deal_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
