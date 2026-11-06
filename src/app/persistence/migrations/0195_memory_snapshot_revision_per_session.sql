-- omnix-migration: phase=expand transactional=true
-- A memory snapshot's revision counts within its chat (MemoryService, idx_omnix_memory_snapshot_owner_session from 0017),
-- but 0004's constraint still made it unique per owner: a character's second chat could not start once memory was on.
ALTER TABLE omnix_memory_snapshots
    DROP CONSTRAINT IF EXISTS omnix_memory_snapshots_workspace_id_owner_type_owner_id_rev_key;

ALTER TABLE omnix_memory_snapshots
    DROP CONSTRAINT IF EXISTS omnix_memory_snapshots_owner_session_revision_key;

ALTER TABLE omnix_memory_snapshots
    ADD CONSTRAINT omnix_memory_snapshots_owner_session_revision_key
        UNIQUE (workspace_id, owner_type, owner_id, session_id, revision);
