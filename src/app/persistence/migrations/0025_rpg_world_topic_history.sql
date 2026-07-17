ALTER TABLE omnix_rpg_world_topics
    DROP CONSTRAINT omnix_rpg_world_topics_pkey;

ALTER TABLE omnix_rpg_world_topics
    ADD PRIMARY KEY (workspace_id, world_id, draft_revision, topic_id);

DROP INDEX IF EXISTS omnix_rpg_world_topics_status_idx;

CREATE INDEX omnix_rpg_world_topics_status_idx
    ON omnix_rpg_world_topics (
        workspace_id, world_id, draft_revision, status, topic_id
    );

ALTER TABLE omnix_rpg_world_generation_runs
    ADD COLUMN parent_run_id TEXT,
    ADD COLUMN lineage_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE omnix_rpg_world_generation_runs
    ADD CONSTRAINT omnix_rpg_world_generation_runs_parent_fk
    FOREIGN KEY (workspace_id, parent_run_id)
    REFERENCES omnix_rpg_world_generation_runs (workspace_id, run_id)
    ON DELETE RESTRICT;

CREATE INDEX omnix_rpg_world_generation_runs_lineage_idx
    ON omnix_rpg_world_generation_runs (
        workspace_id, world_id, draft_revision DESC, parent_run_id
    );

COMMENT ON TABLE omnix_rpg_world_topics IS
    'Revision-preserving reusable-world topic drafts keyed by draft revision.';

COMMENT ON COLUMN omnix_rpg_world_generation_runs.parent_run_id IS
    'Previous draft generation run in the same reusable-world lineage.';

COMMENT ON COLUMN omnix_rpg_world_generation_runs.lineage_jsonb IS
    'Deterministic parent/root and draft lineage metadata for review and rollback.';
