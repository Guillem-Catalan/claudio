-- Fix: migration 010 set atlas_ready in a BEFORE INSERT trigger, but the
-- deal_confirmations row doesn't exist yet at that point. Move the logic
-- to dc_on_deal_created (AFTER INSERT), where the row was just created.

CREATE OR REPLACE FUNCTION dc_on_deal_created()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO deal_confirmations (deal_id, hs_deal_id)
    VALUES (NEW.id, NEW.deal_id)
    ON CONFLICT (deal_id) DO NOTHING;

    IF NEW.crm_id IS NULL THEN
        UPDATE deal_confirmations
        SET atlas_ready = TRUE
        WHERE deal_id = NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Also revert atlas_link_deal to its original form (remove the broken UPDATE)
CREATE OR REPLACE FUNCTION atlas_link_deal()
RETURNS TRIGGER AS $$
DECLARE
    _atlas_id UUID;
BEGIN
    IF NEW.crm_id IS NULL THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE'
       AND NEW.crm_id IS NOT DISTINCT FROM OLD.crm_id
       AND NEW.atlas_id IS NOT NULL THEN
        RETURN NEW;
    END IF;

    SELECT id INTO _atlas_id FROM atlas WHERE crm_id = NEW.crm_id;

    IF NOT FOUND THEN
        INSERT INTO atlas (crm_id)
        VALUES (NEW.crm_id)
        ON CONFLICT (crm_id) DO NOTHING
        RETURNING id INTO _atlas_id;

        IF _atlas_id IS NULL THEN
            SELECT id INTO _atlas_id FROM atlas WHERE crm_id = NEW.crm_id;
        END IF;
    END IF;

    NEW.atlas_id := _atlas_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
