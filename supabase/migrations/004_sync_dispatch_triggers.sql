-- ============================================================================
-- Migration 004: Document all objects created directly in Supabase
-- ============================================================================
-- These were applied via Supabase Dashboard/API during development.
-- This file ensures the repo is the complete source of truth.
-- All statements use IF NOT EXISTS / OR REPLACE to be safely re-runnable.
-- ============================================================================


-- ── 1. Schema corrections (001 had wrong column names for notes) ───────────
-- Actual notes table uses: hs_engagement_id, owner, date, content
-- Migration 001 had: hs_note_id, author, created_hs, content
-- The real table was created with the correct columns; 001 is outdated.
-- No ALTER needed — just documenting the divergence.


-- ── 2. Missing columns on deals ────────────────────────────────────────────

ALTER TABLE deals ADD COLUMN IF NOT EXISTS numero_de_emails INTEGER DEFAULT 0;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS numero_de_calls  INTEGER DEFAULT 0;

-- Pipeline date columns (all 56 columns from sync_deals/properties.py)
-- SDR Partner Opportunities Pipeline
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_prequalified_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_prequalified_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_attempting_to_contact_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_attempting_to_contact_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_associating_the_partner_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_associating_the_partner_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_engaged_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_engaged_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_nurturing_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_nurturing_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_opportunity_lost_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_opportunity_lost_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_to_reschedule_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sdr_to_reschedule_exited DATE;

-- Partners Distribution Pipeline
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_new_deals_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_new_deals_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_demo_booked_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_demo_booked_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_product_alignment_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_product_alignment_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_do_not_use_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_do_not_use_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_pricing_and_packaging_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_pricing_and_packaging_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_contracting_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_contracting_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_closed_pending_payment_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_closed_pending_payment_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_closed_won_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_closed_won_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_on_hold_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_on_hold_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_closed_lost_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_closed_lost_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_to_reschedule_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS dist_to_reschedule_exited DATE;

-- Sales Pipeline
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_meeting_booked_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_meeting_booked_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_discovery_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_discovery_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_to_reschedule_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_to_reschedule_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_product_alignment_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_product_alignment_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_pricing_and_packaging_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_pricing_and_packaging_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_contracting_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_contracting_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_closed_pending_payment_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_closed_pending_payment_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_closed_won_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_closed_won_exited DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_closed_lost_entered DATE;
ALTER TABLE deals ADD COLUMN IF NOT EXISTS sales_closed_lost_exited DATE;


-- ── 3. Missing columns on calls ────────────────────────────────────────────

ALTER TABLE calls ADD COLUMN IF NOT EXISTS hs_call_id TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'modjo';

CREATE UNIQUE INDEX IF NOT EXISTS idx_calls_hs_call_id
    ON calls(hs_call_id)
    WHERE hs_call_id IS NOT NULL;


-- ── 4. Sync dispatch triggers (deals → sync_calls/emails/notes) ────────────
-- Fire when engagement counts increase, dispatching the per-deal sync workflows.

CREATE OR REPLACE FUNCTION dispatch_sync_calls()
RETURNS TRIGGER AS $$
DECLARE
    should_fire BOOLEAN := FALSE;
    _pat TEXT;
BEGIN
    IF TG_OP = 'INSERT' AND COALESCE(NEW.numero_de_calls, 0) > 0 THEN
        should_fire := TRUE;
    ELSIF TG_OP = 'UPDATE' AND COALESCE(NEW.numero_de_calls, 0) > COALESCE(OLD.numero_de_calls, 0) THEN
        should_fire := TRUE;
    END IF;

    IF should_fire THEN
        SELECT decrypted_secret INTO _pat
        FROM vault.decrypted_secrets WHERE name = 'github_pat';

        PERFORM net.http_post(
            url     := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/sync_calls.yml/dispatches',
            headers := jsonb_build_object(
                'Authorization', 'Bearer ' || _pat,
                'Accept', 'application/vnd.github+json'
            ),
            body    := jsonb_build_object(
                'ref', 'main',
                'inputs', jsonb_build_object(
                    'deal_uuid', NEW.id::TEXT,
                    'hs_deal_id', NEW.deal_id
                )
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_deal_calls_changed') THEN
        CREATE TRIGGER trg_deal_calls_changed
            AFTER INSERT OR UPDATE ON deals
            FOR EACH ROW
            EXECUTE FUNCTION dispatch_sync_calls();
    END IF;
END $$;


CREATE OR REPLACE FUNCTION dispatch_sync_emails()
RETURNS TRIGGER AS $$
DECLARE
    should_fire BOOLEAN := FALSE;
    _pat TEXT;
BEGIN
    IF TG_OP = 'INSERT' AND COALESCE(NEW.numero_de_emails, 0) > 0 THEN
        should_fire := TRUE;
    ELSIF TG_OP = 'UPDATE' AND COALESCE(NEW.numero_de_emails, 0) > COALESCE(OLD.numero_de_emails, 0) THEN
        should_fire := TRUE;
    END IF;

    IF should_fire THEN
        SELECT decrypted_secret INTO _pat
        FROM vault.decrypted_secrets WHERE name = 'github_pat';

        PERFORM net.http_post(
            url     := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/sync_emails.yml/dispatches',
            headers := jsonb_build_object(
                'Authorization', 'Bearer ' || _pat,
                'Accept', 'application/vnd.github+json'
            ),
            body    := jsonb_build_object(
                'ref', 'main',
                'inputs', jsonb_build_object(
                    'deal_uuid', NEW.id::TEXT,
                    'hs_deal_id', NEW.deal_id
                )
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_deal_emails_changed') THEN
        CREATE TRIGGER trg_deal_emails_changed
            AFTER INSERT OR UPDATE ON deals
            FOR EACH ROW
            EXECUTE FUNCTION dispatch_sync_emails();
    END IF;
END $$;


CREATE OR REPLACE FUNCTION dispatch_sync_notes()
RETURNS TRIGGER AS $$
DECLARE
    should_fire BOOLEAN := FALSE;
    _pat TEXT;
BEGIN
    IF TG_OP = 'INSERT' AND COALESCE(NEW.numero_de_notas, 0) > 0 THEN
        should_fire := TRUE;
    ELSIF TG_OP = 'UPDATE' AND COALESCE(NEW.numero_de_notas, 0) > COALESCE(OLD.numero_de_notas, 0) THEN
        should_fire := TRUE;
    END IF;

    IF should_fire THEN
        SELECT decrypted_secret INTO _pat
        FROM vault.decrypted_secrets WHERE name = 'github_pat';

        PERFORM net.http_post(
            url     := 'https://api.github.com/repos/guillemcatalan/claudio/actions/workflows/sync_notes.yml/dispatches',
            headers := jsonb_build_object(
                'Authorization', 'Bearer ' || _pat,
                'Accept', 'application/vnd.github+json'
            ),
            body    := jsonb_build_object(
                'ref', 'main',
                'inputs', jsonb_build_object(
                    'deal_uuid', NEW.id::TEXT,
                    'hs_deal_id', NEW.deal_id
                )
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_deal_notes_changed') THEN
        CREATE TRIGGER trg_deal_notes_changed
            AFTER INSERT OR UPDATE ON deals
            FOR EACH ROW
            EXECUTE FUNCTION dispatch_sync_notes();
    END IF;
END $$;


-- ── 5. Email processing dispatch trigger ───────────────────────────────────
-- dispatch_email_processing() already defined in 003.
-- trg_email_inserted was created in Supabase, currently DISABLED for backfill.
-- Documenting its CREATE here for completeness (uses OR REPLACE on function).

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_email_inserted') THEN
        CREATE TRIGGER trg_email_inserted
            AFTER INSERT ON emails
            FOR EACH ROW
            EXECUTE FUNCTION dispatch_email_processing();
    END IF;
END $$;
