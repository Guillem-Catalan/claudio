-- ============================================================================
-- Migration 024: Activate real-time chain
-- ============================================================================
--
-- 1. Update create_audit_stub() — skip onboarding ("session") deals
-- 2. Update dc_on_call_inserted() — skip onboarding deals
-- 3. Disable audit dispatch triggers (audits now run inline)
-- 4. Enable 5 triggers for the sync→context→confirmations→snapshot chain
-- 5. Backfill deal_confirmations for existing deals
-- ============================================================================


-- ── 1. create_audit_stub: skip session deals ────────────────────────────────

CREATE OR REPLACE FUNCTION create_audit_stub()
RETURNS TRIGGER AS $$
DECLARE _deal_name TEXT;
BEGIN
    IF LENGTH(COALESCE(NEW.transcript, '')) < 200 THEN
        RETURN NEW;
    END IF;

    IF NEW.deal_id IS NOT NULL THEN
        SELECT LOWER(deal_name) INTO _deal_name FROM deals WHERE id = NEW.deal_id;
        IF _deal_name LIKE '%session%' THEN
            RETURN NEW;
        END IF;
    END IF;

    IF NEW.rol = 'PBD' THEN
        INSERT INTO pbd_audits (call_ref, call_id, deal_ref, crm_id, hs_deal_id, owner_name)
        VALUES (NEW.id, NEW.call_id, NEW.deal_id, NEW.crm_id, NEW.hs_deal_id, NEW.owner_nombre);
    ELSIF NEW.rol = 'PAE' THEN
        INSERT INTO pae_audits (call_ref, call_id, deal_ref, crm_id, hs_deal_id, owner_name)
        VALUES (NEW.id, NEW.call_id, NEW.deal_id, NEW.crm_id, NEW.hs_deal_id, NEW.owner_nombre);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── 2. dc_on_call_inserted: skip session deals ─────────────────────────────

CREATE OR REPLACE FUNCTION dc_on_call_inserted()
RETURNS TRIGGER AS $$
DECLARE _deal_name TEXT;
BEGIN
    IF NEW.rol IS NOT NULL AND LENGTH(COALESCE(NEW.transcript, '')) >= 200 THEN
        IF NEW.deal_id IS NOT NULL THEN
            SELECT LOWER(deal_name) INTO _deal_name FROM deals WHERE id = NEW.deal_id;
            IF _deal_name LIKE '%session%' THEN
                RETURN NEW;
            END IF;
        END IF;

        UPDATE deal_confirmations
        SET calls_ready = FALSE, front_deal_triggered_at = NULL
        WHERE deal_id = NEW.deal_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── 3. Disable audit dispatch triggers (inline auditing replaces them) ──────

ALTER TABLE pbd_audits DISABLE TRIGGER trg_pbd_audit_stub_created;
ALTER TABLE pae_audits DISABLE TRIGGER trg_pae_audit_stub_created;


-- ── 4. Enable real-time chain triggers ──────────────────────────────────────

ALTER TABLE deals ENABLE TRIGGER trg_atlas_link_deal;
ALTER TABLE deals ENABLE TRIGGER trg_dc_deal_created;
ALTER TABLE deals ENABLE TRIGGER trg_deal_sync_context;
ALTER TABLE calls ENABLE TRIGGER trg_dc_call_inserted;
ALTER TABLE deal_confirmations ENABLE TRIGGER trg_dc_snapshot_ready;


-- ── 5. Backfill deal_confirmations for existing deals ───────────────────────

INSERT INTO deal_confirmations (deal_id, hs_deal_id, calls_ready, emails_ready, notes_ready, atlas_ready)
SELECT d.id, d.deal_id, TRUE, TRUE, TRUE,
       CASE WHEN d.atlas_id IS NOT NULL THEN TRUE ELSE FALSE END
FROM deals d
LEFT JOIN deal_confirmations dc ON dc.deal_id = d.id
WHERE dc.id IS NULL;
