-- omnix-migration: phase=expand transactional=true
-- Evolution roadmap EV-11 (production roadmap §4.1): the proposal record. Work done off the turn (narration's side
-- effects, the game master, an area filled in) is stored as typed proposals, never written to the campaign. A later
-- turn folds every unconsumed proposal of an earlier revision in at load, through its owning rule, and its commit
-- marks each one folded or dropped, conditionally on its still being pending: two racing turns cannot both fold a
-- proposal in. The turn row records the ids it folded in, and replay applies exactly that set. Proposals go with
-- their campaign.
CREATE TABLE IF NOT EXISTS omnix_rpg_proposals (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES omnix_rpg_campaigns(id) ON DELETE CASCADE,
    proposal_id TEXT NOT NULL CHECK (length(proposal_id) BETWEEN 1 AND 300),
    kind TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 80),
    source TEXT NOT NULL CHECK (source IN ('narration', 'game_master', 'area', 'panel')),
    after_revision INTEGER NOT NULL CHECK (after_revision >= 0),
    reason TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 2000),
    payload_jsonb JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'folded', 'dropped')),
    settled_by_turn_id TEXT,
    settled_revision INTEGER,
    drop_reason TEXT CHECK (drop_reason IS NULL OR length(drop_reason) <= 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, campaign_id, proposal_id),
    CHECK ((status = 'pending') = (settled_by_turn_id IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_proposals_pending
    ON omnix_rpg_proposals (workspace_id, campaign_id, after_revision, proposal_id)
    WHERE status = 'pending';

ALTER TABLE omnix_rpg_turns ADD COLUMN IF NOT EXISTS folded_proposals_jsonb JSONB;

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_proposals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_proposals;
CREATE POLICY tenant_isolation ON omnix_rpg_proposals
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');
