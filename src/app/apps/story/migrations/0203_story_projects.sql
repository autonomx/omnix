-- omnix-migration: phase=expand transactional=true
-- Storyteller projects on the server (Storyteller roadmap ST-1.1).
--
-- A project is one story: its premise and settings, the pages of its manuscript, the
-- player's moves in interactive mode, saved versions, and its cast and world notes.
-- Every child row cascades from the project, so purging a trashed project (deleted_at,
-- removed after the retention period by app.apps.story.declarations) removes all of it.
--
-- A job writes its page or version once: source_job_id is unique, so a retried job is a
-- no-op. origin_kind/origin_ref name where an imported project came from (a story asset,
-- an old job's output or the browser's local draft), so running the import again finds
-- the project it already made.

CREATE TABLE IF NOT EXISTS omnix_story_projects (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    premise TEXT NOT NULL DEFAULT '',
    -- writing or interactive.
    mode TEXT NOT NULL DEFAULT 'writing' CHECK (mode IN ('writing', 'interactive')),
    tone TEXT NOT NULL DEFAULT '',
    writing_style TEXT NOT NULL DEFAULT '',
    -- Overrides of the account's StorytellerSettingsProfile read settings; empty uses the account's.
    read_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- new (made here), asset, job or local (the browser's draft before ST-1.4).
    origin_kind TEXT NOT NULL DEFAULT 'new' CHECK (origin_kind IN ('new', 'asset', 'job', 'local')),
    origin_ref TEXT NOT NULL DEFAULT '',
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX IF NOT EXISTS idx_omnix_story_projects_recent
    ON omnix_story_projects (workspace_id, updated_at DESC, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_omnix_story_projects_origin
    ON omnix_story_projects (workspace_id, origin_kind, origin_ref)
    WHERE origin_ref <> '';
CREATE INDEX IF NOT EXISTS idx_omnix_story_projects_trash
    ON omnix_story_projects (deleted_at, id)
    WHERE deleted_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS omnix_story_pages (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter INTEGER NOT NULL DEFAULT 1 CHECK (chapter >= 1),
    position INTEGER NOT NULL CHECK (position >= 0),
    title TEXT NOT NULL DEFAULT '',
    -- [{kind: narration|dialogue, speaker_id?, text}]
    blocks JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- An undone page stays, hidden, so it can be brought back (ST-3.4).
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    source_job_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_omnix_story_pages_order
    ON omnix_story_pages (workspace_id, project_id, chapter, position);

CREATE TABLE IF NOT EXISTS omnix_story_moves (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    -- The page written in answer to this move.
    page_id TEXT,
    player_text TEXT NOT NULL,
    chosen_suggestion TEXT NOT NULL DEFAULT '',
    -- The move this one follows; a second move after the same parent is a branch.
    parent_move_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, page_id) REFERENCES omnix_story_pages (workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, parent_move_id) REFERENCES omnix_story_moves (workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_omnix_story_moves_project
    ON omnix_story_moves (workspace_id, project_id, created_at, id);

CREATE TABLE IF NOT EXISTS omnix_story_versions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('rewrite', 'expand', 'dialogue', 'summarize', 'kept_run', 'manual')),
    title TEXT NOT NULL DEFAULT '',
    -- The whole manuscript as it was: [{chapter, title, blocks}] per page.
    pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_job_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, project_id, version_number),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS omnix_story_characters (
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    traits JSONB NOT NULL DEFAULT '[]'::jsonb,
    role TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, project_id, id),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS omnix_story_notes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('world', 'preset')),
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_story_projects (workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_omnix_story_notes_project
    ON omnix_story_notes (workspace_id, project_id, kind, created_at, id);

-- Row-level security, the same policy as 0106_row_level_security.sql.
ALTER TABLE omnix_story_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_projects FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_projects;
CREATE POLICY tenant_isolation ON omnix_story_projects
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_story_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_pages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_pages;
CREATE POLICY tenant_isolation ON omnix_story_pages
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_story_moves ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_moves FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_moves;
CREATE POLICY tenant_isolation ON omnix_story_moves
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_story_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_versions;
CREATE POLICY tenant_isolation ON omnix_story_versions
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_story_characters ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_characters FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_characters;
CREATE POLICY tenant_isolation ON omnix_story_characters
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_story_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_story_notes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_story_notes;
CREATE POLICY tenant_isolation ON omnix_story_notes
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
