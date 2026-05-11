-- ============================================================================
-- Migration 005: Atlas table + trigger chain
-- ============================================================================
--
-- Chain:
--   deal INSERT/UPDATE → trg_atlas_link_deal (BEFORE) → create stub + set atlas_id
--   atlas INSERT → trg_atlas_stub_created (AFTER) → dispatch atlas.yml
--   atlas UPDATE (last_generated set) → trg_dc_atlas_completed → atlas_ready=TRUE
-- ============================================================================


-- ── 1. Atlas table ─────────────────────────────────────────────────────────

CREATE TABLE atlas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crm_id          TEXT UNIQUE NOT NULL,
    company_name    TEXT,

    -- Company info (direct from HubSpot)
    industry        TEXT,
    company_size    TEXT,
    country         TEXT,
    website         TEXT,
    description     TEXT,

    -- Raw data (formatted text, input for Claude)
    company_info        TEXT,
    deals_breakdown     TEXT,
    contacts_breakdown  TEXT,

    -- Claude-generated output
    deal_history    TEXT,
    contacts_map    TEXT,
    company_context TEXT,

    last_generated  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_atlas_crm_id ON atlas(crm_id);

ALTER TABLE atlas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated read" ON atlas FOR SELECT TO authenticated USING (true);

CREATE TRIGGER trg_atlas_updated_at
    BEFORE UPDATE ON atlas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Re-add FK dropped when atlas was previously removed
ALTER TABLE deals
    ADD CONSTRAINT deals_atlas_id_fkey
    FOREIGN KEY (atlas_id) REFERENCES atlas(id) ON DELETE SET NULL;


-- ── 2. Deal INSERT/UPDATE → create atlas stub + link ───────────────────────
-- BEFORE trigger: sets NEW.atlas_id so the deal row is committed with the link.
-- Creates atlas stub if no row exists for that crm_id.

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

CREATE TRIGGER trg_atlas_link_deal
    BEFORE INSERT OR UPDATE ON deals
    FOR EACH ROW
    EXECUTE FUNCTION atlas_link_deal();


-- ── 3. Atlas stub created → dispatch atlas.yml ─────────────────────────────
-- DISABLED by default — enable when atlas pipeline code is ready.

CREATE OR REPLACE FUNCTION dispatch_atlas_workflow()
RETURNS TRIGGER AS $$
DECLARE
    _pat  TEXT;
    _repo TEXT;
BEGIN
    SELECT decrypted_secret INTO _pat
    FROM vault.decrypted_secrets WHERE name = 'github_pat';

    _repo := current_setting('app.settings.github_repo', true);
    IF _repo IS NULL OR _repo = '' THEN
        _repo := 'guillemcatalan/claudio';
    END IF;

    PERFORM net.http_post(
        url     := 'https://api.github.com/repos/' || _repo || '/actions/workflows/atlas.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _pat,
            'Accept', 'application/vnd.github+json'
        ),
        body    := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'atlas_id', NEW.id::text,
                'crm_id', NEW.crm_id
            )
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_atlas_stub_created
    AFTER INSERT ON atlas
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_atlas_workflow();

ALTER TABLE atlas DISABLE TRIGGER trg_atlas_stub_created;


-- ── 4. Atlas output written → deal_confirmations.atlas_ready = TRUE ────────

CREATE OR REPLACE FUNCTION dc_on_atlas_completed()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.last_generated IS NULL THEN
        RETURN NEW;
    END IF;

    UPDATE deal_confirmations dc
    SET atlas_ready = TRUE
    FROM deals d
    WHERE dc.deal_id = d.id
      AND d.atlas_id = NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_dc_atlas_completed
    AFTER INSERT OR UPDATE ON atlas
    FOR EACH ROW
    EXECUTE FUNCTION dc_on_atlas_completed();
