ALTER TABLE omnix_memory_records
    ADD COLUMN IF NOT EXISTS scope TEXT,
    ADD COLUMN IF NOT EXISTS scope_id TEXT;

UPDATE omnix_memory_records
   SET scope = COALESCE(scope, owner_type),
       scope_id = COALESCE(scope_id, owner_id)
 WHERE scope IS NULL OR scope_id IS NULL;

UPDATE omnix_memory_records
   SET owner_type = 'system',
       owner_id = 'system-assistant'
 WHERE owner_type IN ('global', 'workspace', 'project', 'session');

ALTER TABLE omnix_memory_records
    ALTER COLUMN scope SET NOT NULL,
    ALTER COLUMN scope_id SET NOT NULL;

ALTER TABLE omnix_memory_candidates
    ADD COLUMN IF NOT EXISTS proposed_scope TEXT,
    ADD COLUMN IF NOT EXISTS proposed_scope_id TEXT;

UPDATE omnix_memory_candidates
   SET proposed_scope = COALESCE(proposed_scope, proposed_owner_type),
       proposed_scope_id = COALESCE(proposed_scope_id, proposed_owner_id)
 WHERE proposed_scope IS NULL OR proposed_scope_id IS NULL;

UPDATE omnix_memory_candidates
   SET proposed_owner_type = 'system',
       proposed_owner_id = 'system-assistant'
 WHERE proposed_owner_type IN ('global', 'workspace', 'project', 'session');

ALTER TABLE omnix_memory_candidates
    ALTER COLUMN proposed_scope SET NOT NULL,
    ALTER COLUMN proposed_scope_id SET NOT NULL;

UPDATE omnix_chat_sessions
   SET memory_snapshot_id = NULL
 WHERE memory_snapshot_id IN (
     SELECT id
       FROM omnix_memory_snapshots
      WHERE owner_type IN ('global', 'workspace', 'project', 'session')
         OR session_id IS NULL
 );

DELETE FROM omnix_memory_snapshot_items
 WHERE snapshot_id IN (
     SELECT id
       FROM omnix_memory_snapshots
      WHERE owner_type IN ('global', 'workspace', 'project', 'session')
         OR session_id IS NULL
 );

DELETE FROM omnix_memory_snapshots
 WHERE owner_type IN ('global', 'workspace', 'project', 'session')
    OR session_id IS NULL;

ALTER TABLE omnix_memory_records
    DROP CONSTRAINT IF EXISTS chk_omnix_memory_record_owner_type,
    DROP CONSTRAINT IF EXISTS chk_omnix_memory_record_scope,
    ADD CONSTRAINT chk_omnix_memory_record_owner_type
        CHECK (owner_type IN ('system', 'character')),
    ADD CONSTRAINT chk_omnix_memory_record_scope
        CHECK (scope IN ('global', 'workspace', 'project', 'session'));

ALTER TABLE omnix_memory_candidates
    DROP CONSTRAINT IF EXISTS chk_omnix_memory_candidate_owner_type,
    DROP CONSTRAINT IF EXISTS chk_omnix_memory_candidate_scope,
    ADD CONSTRAINT chk_omnix_memory_candidate_owner_type
        CHECK (proposed_owner_type IN ('system', 'character')),
    ADD CONSTRAINT chk_omnix_memory_candidate_scope
        CHECK (proposed_scope IN ('global', 'workspace', 'project', 'session'));

ALTER TABLE omnix_memory_snapshots
    DROP CONSTRAINT IF EXISTS chk_omnix_memory_snapshot_owner_type,
    ADD CONSTRAINT chk_omnix_memory_snapshot_owner_type
        CHECK (owner_type IN ('system', 'character'));

DROP INDEX IF EXISTS idx_omnix_memory_owner_status;

CREATE INDEX IF NOT EXISTS idx_omnix_memory_owner_scope_status
    ON omnix_memory_records
        (workspace_id, owner_type, owner_id, scope, scope_id, status, pinned DESC, updated_at DESC, id);

CREATE INDEX IF NOT EXISTS idx_omnix_memory_candidate_owner_scope_status
    ON omnix_memory_candidates
        (workspace_id, proposed_owner_type, proposed_owner_id,
         proposed_scope, proposed_scope_id, status, created_at, id);

CREATE INDEX IF NOT EXISTS idx_omnix_memory_snapshot_owner_session
    ON omnix_memory_snapshots
        (workspace_id, owner_type, owner_id, session_id, revision DESC, created_at DESC, id);
