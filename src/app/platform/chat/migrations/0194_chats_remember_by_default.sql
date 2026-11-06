-- omnix-migration: phase=expand transactional=true
-- Existing chats join the owner decision of 2026-11-05: every character and the System Assistant remember across their
-- chats. Set directly: going through set_session_interaction would close each chat's segment and greet again.
-- Whether memory is used at all stays with the memory settings; this only stops a chat from opting out by its age.
UPDATE omnix_chat_sessions
   SET settings = settings || '{"read_memory": true, "write_memory": true}'::jsonb
 WHERE interaction_mode = 'character';

UPDATE omnix_conversation_segments
   SET read_memory = TRUE, write_memory = TRUE
 WHERE interaction_mode = 'character' AND ended_at IS NULL;

UPDATE omnix_chat_sessions
   SET memory_enabled = TRUE
 WHERE interaction_mode = 'system';
