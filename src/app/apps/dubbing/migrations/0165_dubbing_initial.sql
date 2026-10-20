-- omnix-migration: phase=expand transactional=true
-- Dubbing (Voice Studio Phase 6): projects, and the lines a person reviews before the final mix.
--
-- A line keeps its id while its speaker, start and source words stay the same, so a
-- re-run of transcription keeps its translation and approval. Every change to a
-- translation bumps translation_revision; a take records the revision it was rendered
-- from, and an approval records both the revision and the take it approved, so an
-- approval never carries over to words or audio a person did not hear.

CREATE TABLE IF NOT EXISTS omnix_dubbing_projects (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    source_language TEXT NOT NULL DEFAULT 'en',
    target_language TEXT NOT NULL,
    -- The chat provider that translates; empty is the workspace's own (local by default).
    translator TEXT NOT NULL DEFAULT '',
    -- The TTS engine that speaks the dub; empty is the selected engine.
    engine TEXT NOT NULL DEFAULT '',
    speakers INTEGER NOT NULL DEFAULT 0 CHECK (speakers BETWEEN 0 AND 8),
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- Per step: status, job id, error and when it changed (read whole, never queried into).
    steps JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Assets the steps produced: audio, vocals, background, transcript, mix, video, subtitles.
    assets JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Source speaker -> library voice id.
    casting JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX IF NOT EXISTS idx_omnix_dubbing_projects_recent
    ON omnix_dubbing_projects (workspace_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS omnix_dubbing_segments (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    source_key TEXT NOT NULL,
    speaker TEXT NOT NULL,
    start_seconds DOUBLE PRECISION NOT NULL,
    end_seconds DOUBLE PRECISION NOT NULL CHECK (end_seconds > start_seconds),
    source_text TEXT NOT NULL,
    translation TEXT NOT NULL DEFAULT '',
    translation_revision BIGINT NOT NULL DEFAULT 0 CHECK (translation_revision >= 0),
    -- llm, shortened or person.
    translation_origin TEXT NOT NULL DEFAULT '',
    voice_override TEXT NOT NULL DEFAULT '',
    take_asset_id TEXT NOT NULL DEFAULT '',
    take_revision BIGINT NOT NULL DEFAULT 0,
    take_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- pending, fits, stretched, shortened, over or short (see fit.py).
    fit_status TEXT NOT NULL DEFAULT 'pending',
    fit_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
    shortenings INTEGER NOT NULL DEFAULT 0,
    approved_revision BIGINT,
    approved_take_asset_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, project_id, source_key),
    FOREIGN KEY (workspace_id, project_id) REFERENCES omnix_dubbing_projects (workspace_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_omnix_dubbing_segments_order
    ON omnix_dubbing_segments (workspace_id, project_id, position);

-- Row-level security, the same policy as 0106_row_level_security.sql.
ALTER TABLE omnix_dubbing_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_dubbing_projects FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_dubbing_projects;
CREATE POLICY tenant_isolation ON omnix_dubbing_projects
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_dubbing_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_dubbing_segments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_dubbing_segments;
CREATE POLICY tenant_isolation ON omnix_dubbing_segments
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
