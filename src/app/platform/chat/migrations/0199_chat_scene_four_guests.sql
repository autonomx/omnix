-- omnix-migration: phase=expand transactional=true
-- Companion group calls (owner 2026-11-19): a character chat's call seats up to four guests besides its host, five
-- characters in all. Only the seat range widens; seats already taken keep their numbers.
ALTER TABLE omnix_chat_scene_members DROP CONSTRAINT IF EXISTS omnix_chat_scene_members_seat_check;
ALTER TABLE omnix_chat_scene_members ADD CONSTRAINT omnix_chat_scene_members_seat_check CHECK (seat BETWEEN 1 AND 4);
