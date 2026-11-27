-- omnix-migration: phase=expand transactional=true
-- A story handed over from Storyteller (Storyteller roadmap ST-4.4).
--
-- A source imported from a story keeps the story's spoken lines in order with the speaker each was
-- written for. Speaker analysis attributes a dialogue span that matches one of these lines to that
-- speaker; only the spans with no line, or whose line's speaker is not in the cast, go to the
-- classifier. One row per source asset; the source and its lines are immutable together.

CREATE TABLE IF NOT EXISTS omnix_audiobook_story_sources (
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_asset_id TEXT NOT NULL REFERENCES omnix_assets (id),
    story_project_id TEXT NOT NULL CHECK (length(story_project_id) BETWEEN 1 AND 80),
    story_version_id TEXT CHECK (story_version_id IS NULL OR length(story_version_id) BETWEEN 1 AND 80),
    speaker_lines JSONB NOT NULL CHECK (jsonb_typeof(speaker_lines) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, source_asset_id),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_audiobook_projects (workspace_id, id)
);

ALTER TABLE omnix_audiobook_story_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_audiobook_story_sources FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_audiobook_story_sources;
CREATE POLICY tenant_isolation ON omnix_audiobook_story_sources
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
