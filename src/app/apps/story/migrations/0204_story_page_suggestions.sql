-- omnix-migration: phase=expand transactional=true
-- What a story page's model proposes (Storyteller roadmap ST-2.1, ST-2.3).
--
-- A page is written as tagged blocks. The model may also name characters the cast doesn't
-- have and offer the player up to three next moves. A proposed character is kept on the
-- project's cast as a suggestion (suggested = TRUE) until the writer accepts it (FALSE) or
-- dismisses it (the row is removed). A page keeps its suggested moves.

ALTER TABLE omnix_story_characters ADD COLUMN IF NOT EXISTS suggested BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE omnix_story_pages ADD COLUMN IF NOT EXISTS suggested_moves JSONB NOT NULL DEFAULT '[]'::jsonb;
