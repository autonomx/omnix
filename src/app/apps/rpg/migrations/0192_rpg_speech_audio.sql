-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-13: a campaign's spoken audio, cached by its full render identity (the text, the voice and its
-- revision, the provider and model, the language and parameters). Kept in the player's workspace, so no one can
-- probe another's text, and deleted with the campaign. Replaying a response plays from here with no synthesis.
CREATE TABLE IF NOT EXISTS omnix_rpg_speech_audio (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    render_key TEXT NOT NULL CHECK (length(render_key) BETWEEN 1 AND 200),
    voice_id TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT 'audio/wav',
    audio BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, campaign_id, render_key)
);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_speech_audio ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_speech_audio FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_speech_audio;
CREATE POLICY tenant_isolation ON omnix_rpg_speech_audio
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
