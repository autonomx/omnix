-- omnix-migration: phase=expand transactional=true
-- A take remembers whether it came out near-silent (owner 2026-11-24): the render that kept its loudest try after
-- every retry lacked the words says so when it stores the take, and a later render speaks the line again without
-- reading and measuring the take's audio. Takes stored before this have no answer (NULL) and are still measured.
ALTER TABLE omnix_voice_takes ADD COLUMN IF NOT EXISTS near_silent BOOLEAN NULL;
