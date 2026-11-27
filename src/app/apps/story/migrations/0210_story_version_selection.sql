-- omnix-migration: phase=expand transactional=true
-- A version that proposes a change to a selection of one page (Storyteller roadmap ST-6.2).
--
-- selection is null for a whole-manuscript version. For a selection it is {page_id, start, end, original,
-- proposed, status}: the blocks [start, end) of the page as they were when the job ran, the blocks the job
-- proposes in their place, and whether the writer has accepted or rejected the change ('pending' until then).
-- The version's pages are the manuscript with the change made, so it compares and restores like any other.

ALTER TABLE omnix_story_versions ADD COLUMN IF NOT EXISTS selection JSONB;
