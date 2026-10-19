-- omnix-migration: phase=expand transactional=true
-- Row-level security for the desktop sign-in handoffs (0161), like every other table with workspace_id (WP-4.4).
--
-- Sign-in reads and writes the handoffs before a tenant exists, inside the auth.sessions system scope
-- (AuthService._work), so the system branch of the policy keeps that working. A connection scoped to a
-- workspace sees only the handoffs that completed into it, and none still in flight (workspace_id NULL).

ALTER TABLE omnix_auth_desktop_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_auth_desktop_handoffs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_auth_desktop_handoffs;
CREATE POLICY tenant_isolation ON omnix_auth_desktop_handoffs
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
