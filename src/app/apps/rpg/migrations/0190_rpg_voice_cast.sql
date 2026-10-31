-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-13: a campaign's voice cast. The narrator and each person who speaks are given a castable voice,
-- pinned by its revision (a hash of its reference recording and transcript): automatically, by the world's author, or
-- by the player, whose choice wins. The cast is presentation, not the game's state: it is kept here, outside the
-- campaign document, so it changes no turn and touches no replay. Rows go with their campaign.
CREATE TABLE IF NOT EXISTS omnix_rpg_voice_cast (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    speaker_id TEXT NOT NULL CHECK (length(speaker_id) BETWEEN 1 AND 200),
    voice_id TEXT NOT NULL CHECK (length(voice_id) BETWEEN 1 AND 200),
    voice_revision TEXT NOT NULL DEFAULT '',
    chosen_by TEXT NOT NULL DEFAULT 'auto' CHECK (chosen_by IN ('auto', 'author', 'player')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, campaign_id, speaker_id)
);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_voice_cast ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_voice_cast FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_voice_cast;
CREATE POLICY tenant_isolation ON omnix_rpg_voice_cast
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
