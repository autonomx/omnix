-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-0 (part 2): the world's lore review queue. What the game master invents in a campaign is played
-- there at once, from the campaign's lore layer (its document); where question 15 says so (a world the player owns, or
-- one whose owner asked for drafts; never a guest's campaign) it is also filed here, in the world owner's workspace,
-- as a draft for the author: the entry and its play data together, the consistency check's findings (the author's
-- evidence, never a verdict), and the author's decision. An approved entry joins the world at its next publication
-- under a canon id; a rejected one stays in the campaign that met it. Drafts with the same or a close name share a
-- group key, so an author approves one and links the others.
CREATE TABLE IF NOT EXISTS omnix_rpg_lore_review (
    id BIGSERIAL PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    world_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    entry_id TEXT NOT NULL CHECK (length(entry_id) BETWEEN 1 AND 200),
    family TEXT NOT NULL CHECK (family IN ('person', 'place', 'item', 'creature', 'quest')),
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    group_key TEXT NOT NULL,
    entry_jsonb JSONB NOT NULL,
    provenance_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'linked')),
    findings_jsonb JSONB,
    canon_id TEXT NOT NULL DEFAULT '',
    linked_to BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMPTZ,
    UNIQUE (workspace_id, campaign_id, entry_id)
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_lore_review_world
    ON omnix_rpg_lore_review (workspace_id, world_id, status, group_key, id);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_lore_review ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_lore_review FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_lore_review;
CREATE POLICY tenant_isolation ON omnix_rpg_lore_review
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
