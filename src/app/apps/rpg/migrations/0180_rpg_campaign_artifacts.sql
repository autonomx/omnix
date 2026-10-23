-- omnix-migration: phase=expand transactional=true
-- RQ-1.1 (docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md §4.2): what a campaign's creation produced and no turn
-- reads (a World Forge campaign's compiled genesis and bootstrap snapshot, 0.5 MB together) is kept once,
-- here, instead of three times inside the campaign document that every turn loads, copies and saves.
-- One row per campaign and kind; it goes with its campaign.
CREATE TABLE IF NOT EXISTS omnix_rpg_campaign_artifacts (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 100),
    document_jsonb JSONB NOT NULL,
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, campaign_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_campaign_artifacts_campaign
    ON omnix_rpg_campaign_artifacts (campaign_id);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_campaign_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_campaign_artifacts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_campaign_artifacts;
CREATE POLICY tenant_isolation ON omnix_rpg_campaign_artifacts
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
