-- omnix-migration: phase=expand transactional=true
-- A guest seat expires after its call ends (2026-11-20): a call stamps its seats while it is open, and a seat whose
-- call has been quiet past the expiry no longer counts. A seat chosen before any call has no stamp and stays. The
-- browser still clears the seats when a call ends; this covers a tab that crashed or closed mid-call.
ALTER TABLE omnix_chat_scene_members ADD COLUMN IF NOT EXISTS last_call_at timestamptz NULL;
