-- omnix-migration: phase=expand transactional=true
-- RQ-1.4 (docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md §4.1 "Narration is outside the campaign document"): what was
-- narrated for a turn is kept here, keyed by the turn and its kind, instead of in the campaign document's
-- runtime_state.narration_artifacts. A narration that finishes after its turn committed is written here alone,
-- so it is not a campaign revision and cannot collide with the player's next turn.
CREATE TABLE IF NOT EXISTS omnix_rpg_turn_narrations (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL CHECK (length(turn_id) BETWEEN 1 AND 300),
    kind TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 100),
    document_jsonb JSONB NOT NULL,
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, campaign_id, turn_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_turn_narrations_recent
    ON omnix_rpg_turn_narrations (workspace_id, campaign_id, updated_at DESC);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_turn_narrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_turn_narrations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_turn_narrations;
CREATE POLICY tenant_isolation ON omnix_rpg_turn_narrations
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
