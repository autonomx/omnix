-- omnix-migration: phase=expand transactional=true
-- Voice Studio Phase 1 §5: saved scripts, lines with a stable identity, and every take.
--
-- A line keeps its id while the same speaker says the same words, so one line can be
-- rendered again and the full render rebuilt from each line's selected take
-- (voice.restitch). Takes point at stored audio assets; deleting a line removes its
-- takes but never the audio assets.

CREATE TABLE IF NOT EXISTS omnix_voice_scripts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT '',
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (workspace_id, id)
);

CREATE INDEX IF NOT EXISTS idx_omnix_voice_scripts_recent
    ON omnix_voice_scripts (workspace_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS omnix_voice_script_lines (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    script_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    pause_before_ms INTEGER CHECK (pause_before_ms IS NULL OR (pause_before_ms >= 0 AND pause_before_ms <= 10000)),
    delivery_instruction TEXT NOT NULL DEFAULT '',
    voice_id TEXT NOT NULL DEFAULT '',
    selected_take_id TEXT,
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, script_id) REFERENCES omnix_voice_scripts (workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_omnix_voice_script_lines_order
    ON omnix_voice_script_lines (workspace_id, script_id, position);

CREATE TABLE IF NOT EXISTS omnix_voice_takes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    script_id TEXT NOT NULL,
    line_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    job_id TEXT,
    engine TEXT NOT NULL DEFAULT '',
    text_hash TEXT NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (workspace_id, line_id) REFERENCES omnix_voice_script_lines (workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, script_id) REFERENCES omnix_voice_scripts (workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_omnix_voice_takes_line
    ON omnix_voice_takes (workspace_id, line_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_omnix_voice_takes_script
    ON omnix_voice_takes (workspace_id, script_id, created_at DESC);

ALTER TABLE omnix_voice_scripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_scripts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_scripts;
CREATE POLICY tenant_isolation ON omnix_voice_scripts
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_voice_script_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_script_lines FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_script_lines;
CREATE POLICY tenant_isolation ON omnix_voice_script_lines
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

ALTER TABLE omnix_voice_takes ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_voice_takes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_voice_takes;
CREATE POLICY tenant_isolation ON omnix_voice_takes
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
