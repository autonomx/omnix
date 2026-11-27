-- omnix-migration: phase=expand transactional=true
-- A story's plan and its prompt presets (Storyteller roadmap ST-5.1, ST-5.2).
--
-- outline is the plan the writer edits: [{chapter, title, beats: [{id, text, page_id}]}]. A planning job
-- writes it once (outline_source_job_id, so a retried job writes nothing twice), and a beat drafted into a
-- page keeps that page's id. A preset is a note (kind 'preset') with a tone, a writing style and its
-- instructions; preset_id is the one the project writes with ('' for none).

ALTER TABLE omnix_story_projects ADD COLUMN IF NOT EXISTS outline JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE omnix_story_projects ADD COLUMN IF NOT EXISTS outline_source_job_id TEXT;
ALTER TABLE omnix_story_projects ADD COLUMN IF NOT EXISTS preset_id TEXT NOT NULL DEFAULT '';

ALTER TABLE omnix_story_notes ADD COLUMN IF NOT EXISTS tone TEXT NOT NULL DEFAULT '';
ALTER TABLE omnix_story_notes ADD COLUMN IF NOT EXISTS writing_style TEXT NOT NULL DEFAULT '';
