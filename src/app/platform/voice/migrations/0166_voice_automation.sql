-- omnix-migration: phase=expand transactional=true
-- Voice Studio Phase 7: recipes, batch runs, watch folders and inbound client credentials.
--
-- A recipe is a named, versioned list of tool steps. A batch run fans out one item per input;
-- each item submits ordinary jobs, one step at a time, so no parent job holds a pool slot.
-- Watch folders are operator configuration (not stored here); their ledger is, unique per
-- workspace, folder, relative path and content hash, so a restart never processes a file twice.
-- Client credentials are per-client tokens (stored as hashes) bound to a workspace, an owner
-- and a capability ceiling.

CREATE TABLE IF NOT EXISTS omnix_voice_recipes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_recipes_recent ON omnix_voice_recipes (workspace_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS omnix_voice_batch_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    owner_user_id TEXT,
    recipe_id TEXT NOT NULL,
    recipe_version INTEGER NOT NULL,
    -- The recipe's steps as they were when the run started.
    steps JSONB NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    -- The watch folder that feeds the run, when one does.
    watch_folder TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_batch_runs_active ON omnix_voice_batch_runs (status, updated_at);

CREATE TABLE IF NOT EXISTS omnix_voice_batch_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    source_asset_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    -- The asset each step consumes: the source, then each step's output.
    current_asset_id TEXT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed', 'skipped')),
    job_id TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    outputs JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT NOT NULL DEFAULT '',
    -- Where a watch folder wants the outputs written (relative to its output folder).
    output_name TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (workspace_id, run_id) REFERENCES omnix_voice_batch_runs (workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_batch_items_run ON omnix_voice_batch_items (workspace_id, run_id, position);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_batch_items_active ON omnix_voice_batch_items (status, updated_at);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_batch_items_done
    ON omnix_voice_batch_items (workspace_id, input_hash) WHERE status = 'done';

CREATE TABLE IF NOT EXISTS omnix_voice_watch_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    folder_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    batch_item_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, folder_id, relative_path, content_hash)
);

-- One watcher per folder at a time: a fenced lease, like the swap lease (0164). Watch folders
-- are operator configuration shared by the device, not workspace data.
CREATE TABLE IF NOT EXISTS omnix_voice_watch_leases (
    folder_id TEXT PRIMARY KEY,
    holder_id TEXT NOT NULL,
    fence_token BIGINT NOT NULL DEFAULT 1,
    lease_expires_at TIMESTAMPTZ NOT NULL
);
COMMENT ON TABLE omnix_voice_watch_leases IS 'omnix:tenant-exempt: watch-folder leases are device coordination, not workspace data';

CREATE TABLE IF NOT EXISTS omnix_voice_client_credentials (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    -- SHA-256 of the token; the token itself is shown once and never stored.
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    capabilities TEXT[] NOT NULL,
    caps_digest TEXT NOT NULL CHECK (length(caps_digest) = 64),
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_client_credentials_workspace
    ON omnix_voice_client_credentials (workspace_id, created_at DESC);

-- Row-level security, the same policy as 0106_row_level_security.sql. The credential lookup by
-- hash runs before a tenant exists, inside a narrow system scope (the 0162 pattern).
ALTER TABLE omnix_voice_recipes ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_recipes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_recipes;
CREATE POLICY tenant_isolation ON omnix_voice_recipes
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_voice_batch_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_batch_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_batch_runs;
CREATE POLICY tenant_isolation ON omnix_voice_batch_runs
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_voice_batch_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_batch_items FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_batch_items;
CREATE POLICY tenant_isolation ON omnix_voice_batch_items
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_voice_watch_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_watch_items FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_watch_items;
CREATE POLICY tenant_isolation ON omnix_voice_watch_items
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_voice_client_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_client_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_client_credentials;
CREATE POLICY tenant_isolation ON omnix_voice_client_credentials
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
