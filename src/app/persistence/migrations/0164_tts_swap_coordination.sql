-- omnix-migration: phase=expand transactional=true
-- Voice Studio Phase 1 §6: swap, don't stack, on one GPU.
--
-- 1. Device permits gain an `audio` model class (separation, enhancement, watermarking).
-- 2. omnix_tts_live_sessions: a durable, expiring lease held for the whole of a live call or
--    chat read-aloud. A swap never starts while one exists, so the swap controller can see
--    live speech in any process (permit holders exist only during one generation call).
-- 3. omnix_tts_swap_state: the one swap at a time (fence token, the engine swapped in, the
--    engine to restore, an expiring lease) that recovery reads after a crash.
-- 4. omnix_tts_swap_requests: jobs that need an engine other than the loaded one, waiting in
--    arrival order.
-- The GPU is one device shared by every workspace, so these coordination rows are not
-- tenant data (like the device permit tables).

ALTER TABLE omnix_device_capacity DROP CONSTRAINT IF EXISTS omnix_device_capacity_model_class_check;
ALTER TABLE omnix_device_capacity
    ADD CONSTRAINT omnix_device_capacity_model_class_check
    CHECK (model_class IN ('tts', 'stt', 'image', 'llm-local', 'audio'));

CREATE TABLE IF NOT EXISTS omnix_tts_live_sessions (
    session_id TEXT PRIMARY KEY,
    holder_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('live_call', 'read_aloud', 'realtime')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_omnix_tts_live_sessions_expiry ON omnix_tts_live_sessions (expires_at);
COMMENT ON TABLE omnix_tts_live_sessions IS 'omnix:tenant-exempt: GPU live-speech leases shared by every workspace on the device';

CREATE TABLE IF NOT EXISTS omnix_tts_swap_state (
    model_class TEXT PRIMARY KEY CHECK (model_class = 'tts'),
    fence_token BIGINT NOT NULL DEFAULT 0,
    phase TEXT NOT NULL DEFAULT 'idle' CHECK (phase IN ('idle', 'swapping', 'active', 'restoring')),
    holder_id TEXT,
    engine TEXT,
    restore_engine TEXT,
    lease_expires_at TIMESTAMPTZ,
    group_started_at TIMESTAMPTZ,
    interrupted BOOLEAN NOT NULL DEFAULT FALSE,
    detail TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO omnix_tts_swap_state (model_class) VALUES ('tts') ON CONFLICT (model_class) DO NOTHING;
COMMENT ON TABLE omnix_tts_swap_state IS 'omnix:tenant-exempt: the GPU swap lease shared by every workspace on the device';

CREATE TABLE IF NOT EXISTS omnix_tts_swap_requests (
    id TEXT PRIMARY KEY,
    engine TEXT NOT NULL,
    job_id TEXT NOT NULL,
    -- pending: waiting; served: the engine is loaded and the job runs on it; done: the job finished.
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'served', 'done', 'failed')),
    detail TEXT NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_omnix_tts_swap_requests_job_pending
    ON omnix_tts_swap_requests (job_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_omnix_tts_swap_requests_queue
    ON omnix_tts_swap_requests (status, requested_at, id);
COMMENT ON TABLE omnix_tts_swap_requests IS 'omnix:tenant-exempt: GPU engine swap requests shared by every workspace on the device';
