-- omnix-migration: phase=expand transactional=true
-- RQ-5.7 (docs/rpg/design/rewind.md): a save point is a pinned snapshot the player named. Restoring one rewinds the
-- campaign to its revision as a new revision; deleting one clears its name and unpins it. At most one snapshot of a
-- campaign carries a given name.
ALTER TABLE omnix_rpg_snapshots
    ADD COLUMN IF NOT EXISTS save_point_name TEXT
        CHECK (save_point_name IS NULL OR length(save_point_name) BETWEEN 1 AND 80);

CREATE UNIQUE INDEX IF NOT EXISTS omnix_rpg_snapshots_save_point_name
    ON omnix_rpg_snapshots (workspace_id, campaign_id, save_point_name)
    WHERE save_point_name IS NOT NULL;
