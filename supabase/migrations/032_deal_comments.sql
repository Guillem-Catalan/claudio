-- ============================================================================
-- Migration 032: Deal Comments
-- ============================================================================
-- User feedback on deals from the Next Steps modal.
-- Stored in Supabase, forwarded to Slack via pg_net trigger.
-- `solution` column filled manually — not used by triggers or frontend.
-- ============================================================================

CREATE TABLE deal_comments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id     UUID REFERENCES deals(id) ON DELETE CASCADE,
    deal_name   TEXT,
    author_name TEXT NOT NULL,
    body        TEXT NOT NULL,
    solution    TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_deal_comments_deal ON deal_comments(deal_id);

ALTER TABLE deal_comments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anon read"   ON deal_comments FOR SELECT TO anon USING (true);
CREATE POLICY "Anon insert" ON deal_comments FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "Service all" ON deal_comments FOR ALL TO service_role USING (true);

-- ── Slack notification via pg_net ───────────────────────────────────────────
-- Requires: SELECT vault.create_secret('slack_bot_token', 'xoxb-...');

CREATE OR REPLACE FUNCTION notify_comment_slack()
RETURNS TRIGGER AS $$
DECLARE _token TEXT;
BEGIN
    SELECT decrypted_secret INTO _token
    FROM vault.decrypted_secrets WHERE name = 'slack_bot_token';

    IF _token IS NULL THEN
        RAISE WARNING 'slack_bot_token not found in vault';
        RETURN NEW;
    END IF;

    PERFORM net.http_post(
        url     := 'https://slack.com/api/chat.postMessage',
        body    := jsonb_build_object(
            'channel', 'C0ATY3V8CN4',
            'text', format(
                E'\xF0\x9F\x92\xAC *%s* — comentario de %s\n> %s',
                NEW.deal_name, NEW.author_name, NEW.body
            )
        ),
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || _token,
            'Content-Type', 'application/json'
        )
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_comment_slack
    AFTER INSERT ON deal_comments
    FOR EACH ROW EXECUTE FUNCTION notify_comment_slack();
