-- omnix-migration: phase=expand transactional=true
-- A reading of a stretch of conversation: what the character took from it. The
-- relationship, moods, episodes, notes on the person and connections between
-- facts are all derived from these, so forgetting one rebuilds them.
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT c.conname INTO constraint_name
      FROM pg_constraint c
     WHERE c.conrelid = 'omnix_memory_v2_observations'::regclass
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%event_type%';
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE omnix_memory_v2_observations DROP CONSTRAINT %I', constraint_name);
    END IF;
END $$;

ALTER TABLE omnix_memory_v2_observations
    ADD CONSTRAINT omnix_memory_v2_observations_event_type_check CHECK (event_type IN (
        'user_said', 'assistant_generated', 'assistant_delivered',
        'assistant_experienced', 'external_observed', 'system_event',
        'imported_legacy_memory', 'acoustic_observation', 'curated_memory',
        'conversation_reading'
    ));

-- The sweep that finds conversations to read scans only these.
CREATE INDEX IF NOT EXISTS idx_omnix_memory_v2_observations_conversation
    ON omnix_memory_v2_observations (principal_id, owner_type, owner_id, authority_sequence)
    WHERE event_type IN ('user_said', 'assistant_generated', 'conversation_reading');

-- Forgetting a chat finds its turns and readings by the chat they came from.
CREATE INDEX IF NOT EXISTS idx_omnix_memory_v2_observations_session
    ON omnix_memory_v2_observations (principal_id, owner_type, owner_id, (provenance->>'session_id'))
    WHERE event_type IN ('user_said', 'assistant_generated', 'conversation_reading');
