-- omnix-migration: phase=expand transactional=true
-- An interactive run's branches and its rolling summary (Storyteller roadmap ST-3.3, ST-3.4).
--
-- parent_page_id is the page a page continued from: the last visible page when it was written,
-- NULL for a story's first page. The visible run is one chain of parents, so undoing a move
-- hides the newest page and opening an earlier page shows the chain that ends there; every
-- hidden page stays and can be opened again as a branch.
--
-- summary is the model's account of the story so far, through that page. A page's prompt carries
-- the summary of the page before it rather than the whole story, and each branch keeps its own.

ALTER TABLE omnix_story_pages ADD COLUMN IF NOT EXISTS parent_page_id TEXT;

ALTER TABLE omnix_story_pages ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
