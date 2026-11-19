-- omnix-migration: phase=expand transactional=true
-- Characters talking to each other on a call (companion 6.2): one row per scene talk attempt, keyed by the
-- initiative lease it ran under. The hourly cap counts an account's line and start attempts; a declined or
-- skipped line or reaction closes its anchor; a declined or skipped start backs off further starts in its chat.
-- Rows older than a day are pruned on write. Like the module's other tables, no RLS: only the initiative
-- authority reads and writes it.
CREATE TABLE IF NOT EXISTS omnix_companion_scene_talk_attempts (
    attempt_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    anchor_message_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('reaction', 'line', 'start')),
    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('streamed', 'declined', 'skipped', 'failed')),
    streamed_text TEXT CHECK (streamed_text IS NULL OR char_length(streamed_text) <= 240),
    next_start_after TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS omnix_companion_scene_talk_attempts_user_idx
    ON omnix_companion_scene_talk_attempts(user_id, created_at);

CREATE INDEX IF NOT EXISTS omnix_companion_scene_talk_attempts_closed_idx
    ON omnix_companion_scene_talk_attempts(session_id, anchor_message_id)
    WHERE kind IN ('reaction', 'line') AND outcome IN ('declined', 'skipped');

CREATE INDEX IF NOT EXISTS omnix_companion_scene_talk_attempts_backoff_idx
    ON omnix_companion_scene_talk_attempts(session_id, next_start_after)
    WHERE kind = 'start' AND next_start_after IS NOT NULL;
