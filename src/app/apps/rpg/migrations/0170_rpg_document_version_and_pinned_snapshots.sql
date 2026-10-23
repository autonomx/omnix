-- omnix-migration: phase=expand transactional=true
-- RQ-1.7 / RQ-1.1 (docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md §4.2): a turn row's
-- schema_version holds the session's save_version, not the campaign document's
-- version, so turns and snapshots gain document_version (null for rows written
-- before it). A pinned snapshot (the pre-upgrade backup, the upcast boundary,
-- a compaction base) is never deleted by snapshot retention.
ALTER TABLE omnix_rpg_snapshots ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE omnix_rpg_snapshots ADD COLUMN IF NOT EXISTS document_version INTEGER;
ALTER TABLE omnix_rpg_turns ADD COLUMN IF NOT EXISTS document_version INTEGER;
