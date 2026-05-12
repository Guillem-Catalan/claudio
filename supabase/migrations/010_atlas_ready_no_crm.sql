-- When a deal has no crm_id, it can never get an atlas.
-- Set atlas_ready = TRUE so the deal isn't blocked forever.

CREATE OR REPLACE FUNCTION atlas_link_deal()
RETURNS TRIGGER AS $$
DECLARE
    _atlas_id UUID;
BEGIN
    IF NEW.crm_id IS NULL THEN
        UPDATE deal_confirmations
        SET atlas_ready = TRUE
        WHERE deal_id = NEW.id;
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
