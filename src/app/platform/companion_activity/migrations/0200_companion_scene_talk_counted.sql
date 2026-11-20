-- omnix-migration: phase=expand transactional=true
-- Companion group calls (owner 2026-11-19): the lines that follow a person's message, while the characters answer
-- them, no longer use up the account's hourly scene talk attempts; only quiet-call starts and the lines of a talk
-- the characters started do. Such a thread stays bounded by its line limit and by a declined or skipped line.
-- Existing rows keep counting.
ALTER TABLE omnix_companion_scene_talk_attempts ADD COLUMN IF NOT EXISTS counted BOOLEAN NOT NULL DEFAULT true;
