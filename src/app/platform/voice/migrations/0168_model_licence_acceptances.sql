-- omnix-migration: phase=expand transactional=true
-- Desktop roadmap D-4 and DT-2.3: every model installs only after its licence is accepted, and the acceptance is
-- recorded here, per workspace and user, for the exact pinned revision the catalog names. A catalog update that
-- changes a model's revision or licence needs a new acceptance. The install job reads this table; the model's
-- install marker on disk only mirrors it.

CREATE TABLE IF NOT EXISTS omnix_model_licence_acceptances (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    licence_id TEXT NOT NULL,
    licence_url TEXT NOT NULL DEFAULT '',
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, model_id, revision, user_id)
);

CREATE INDEX IF NOT EXISTS idx_omnix_model_licence_acceptances_model
    ON omnix_model_licence_acceptances (workspace_id, model_id, revision);

ALTER TABLE omnix_model_licence_acceptances ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_model_licence_acceptances FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_model_licence_acceptances;
CREATE POLICY tenant_isolation ON omnix_model_licence_acceptances
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
