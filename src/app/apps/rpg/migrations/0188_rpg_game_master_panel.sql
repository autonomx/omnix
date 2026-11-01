-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-0 (part 1): the game master's panel. The player asks the game master about the campaign; each
-- question and the answer shown (or that it was withheld, an answer that would have told a secret or something the
-- hero does not know) is kept here, outside the campaign document: a question changes no state, so replay needs none
-- of it. The developer view and the gate read it, and its questions count, with turns, against the player's hourly
-- model budget (RQ-8.2). Entries go with their campaign.
CREATE TABLE IF NOT EXISTS omnix_rpg_game_master_panel (
    id BIGSERIAL PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL CHECK (revision >= 0),
    question TEXT NOT NULL CHECK (length(question) BETWEEN 1 AND 1000),
    answer TEXT NOT NULL CHECK (length(answer) <= 4000),
    withheld BOOLEAN NOT NULL DEFAULT FALSE,
    wish_jsonb JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_game_master_panel_campaign
    ON omnix_rpg_game_master_panel (workspace_id, campaign_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_omnix_rpg_game_master_panel_owner_recent
    ON omnix_rpg_game_master_panel (workspace_id, owner_user_id, created_at DESC);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_game_master_panel ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_game_master_panel FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_game_master_panel;
CREATE POLICY tenant_isolation ON omnix_rpg_game_master_panel
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
