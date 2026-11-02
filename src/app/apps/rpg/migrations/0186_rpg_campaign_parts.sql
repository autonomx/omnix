-- omnix-migration: phase=expand transactional=true
-- Roadmap §7 Q-13 (F2): a campaign document is stored as its head (omnix_rpg_campaigns.state_jsonb) and its parts,
-- here: each large entry of a top-level section (/runtime_state/player_journal) is a row, so a turn rewrites only
-- the parts it changed instead of the whole document (app.apps.rpg.foundation.persistence.document_parts). A
-- campaign stored before this has no parts: its head is the whole document until its next write. Parts go with
-- their campaign.
--
-- A document's hash is now the hash of its entries' hashes, written "e1:" and 64 hex digits, so a turn hashes only
-- what it changed; a hash written before is the whole text's sha256 (64 hex digits) and stays valid in history.
ALTER TABLE omnix_rpg_campaigns DROP CONSTRAINT IF EXISTS omnix_rpg_campaigns_state_hash_check;
ALTER TABLE omnix_rpg_campaigns ADD CONSTRAINT omnix_rpg_campaigns_state_hash_check
    CHECK (length(state_hash) = 64 OR (left(state_hash, 3) = 'e1:' AND length(state_hash) = 67));
ALTER TABLE omnix_rpg_turns DROP CONSTRAINT IF EXISTS omnix_rpg_turns_state_hash_before_check;
ALTER TABLE omnix_rpg_turns ADD CONSTRAINT omnix_rpg_turns_state_hash_before_check
    CHECK (length(state_hash_before) = 64 OR (left(state_hash_before, 3) = 'e1:' AND length(state_hash_before) = 67));
ALTER TABLE omnix_rpg_turns DROP CONSTRAINT IF EXISTS omnix_rpg_turns_state_hash_after_check;
ALTER TABLE omnix_rpg_turns ADD CONSTRAINT omnix_rpg_turns_state_hash_after_check
    CHECK (length(state_hash_after) = 64 OR (left(state_hash_after, 3) = 'e1:' AND length(state_hash_after) = 67));
ALTER TABLE omnix_rpg_snapshots DROP CONSTRAINT IF EXISTS omnix_rpg_snapshots_state_hash_check;
ALTER TABLE omnix_rpg_snapshots ADD CONSTRAINT omnix_rpg_snapshots_state_hash_check
    CHECK (length(state_hash) = 64 OR (left(state_hash, 3) = 'e1:' AND length(state_hash) = 67));

CREATE TABLE IF NOT EXISTS omnix_rpg_campaign_parts (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    path TEXT NOT NULL CHECK (length(path) BETWEEN 3 AND 1000),
    part_hash TEXT NOT NULL CHECK (length(part_hash) = 64),
    part_jsonb JSONB NOT NULL,
    PRIMARY KEY (workspace_id, campaign_id, path)
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_campaign_parts_campaign
    ON omnix_rpg_campaign_parts (campaign_id);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_settings
         WHERE name = 'default_toast_compression' AND 'lz4' = ANY(enumvals)
    ) THEN
        ALTER TABLE omnix_rpg_campaign_parts ALTER COLUMN part_jsonb SET COMPRESSION lz4;
    END IF;
END $$;

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_campaign_parts ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_campaign_parts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_campaign_parts;
CREATE POLICY tenant_isolation ON omnix_rpg_campaign_parts
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
