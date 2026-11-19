-- omnix-migration: phase=expand transactional=true
-- Companion 5.1: the characters a person has added to a character chat's call, besides its own character (the host).
-- A guest leaves the scene when its chat or its character is deleted. At most two guests, in seat order.
CREATE TABLE IF NOT EXISTS omnix_chat_scene_members (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES omnix_chat_sessions(id) ON DELETE CASCADE,
    character_id TEXT NOT NULL REFERENCES omnix_characters(id) ON DELETE CASCADE,
    seat SMALLINT NOT NULL CHECK (seat BETWEEN 1 AND 2),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, character_id),
    UNIQUE (session_id, seat)
);

CREATE INDEX IF NOT EXISTS omnix_chat_scene_members_character_idx
    ON omnix_chat_scene_members (workspace_id, character_id);

ALTER TABLE omnix_chat_scene_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_chat_scene_members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_chat_scene_members;
CREATE POLICY tenant_isolation ON omnix_chat_scene_members
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
