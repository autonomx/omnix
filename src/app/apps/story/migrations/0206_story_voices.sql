-- omnix-migration: phase=expand transactional=true
-- A story's voices (Storyteller roadmap ST-4.2).
--
-- omnix_story_voice_cast gives the narrator and each character of a project a castable voice,
-- pinned by its revision (a hash of its reference recording and transcript): automatically,
-- matched to the character's description, or by the writer, whose choice wins.
--
-- omnix_story_speech_audio keeps each spoken sentence by its full render identity (its text,
-- the voice and its revision, the provider, model and parameters), so a page played again
-- plays from here. page_id is the page it was first spoken for. Both are in the writer's
-- workspace and go with the project.

CREATE TABLE IF NOT EXISTS omnix_story_voice_cast (
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    speaker_id TEXT NOT NULL CHECK (length(speaker_id) BETWEEN 1 AND 200),
    voice_id TEXT NOT NULL CHECK (length(voice_id) BETWEEN 1 AND 200),
    voice_revision TEXT NOT NULL DEFAULT '',
    chosen_by TEXT NOT NULL DEFAULT 'auto' CHECK (chosen_by IN ('auto', 'writer')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, project_id, speaker_id),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS omnix_story_speech_audio (
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    render_key TEXT NOT NULL CHECK (length(render_key) BETWEEN 1 AND 200),
    page_id TEXT NOT NULL DEFAULT '',
    voice_id TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT 'audio/wav',
    audio BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, project_id, render_key),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE
);

ALTER TABLE omnix_story_voice_cast ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_voice_cast FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_voice_cast;
CREATE POLICY tenant_isolation ON omnix_story_voice_cast
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_story_speech_audio ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_speech_audio FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_speech_audio;
CREATE POLICY tenant_isolation ON omnix_story_speech_audio
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
