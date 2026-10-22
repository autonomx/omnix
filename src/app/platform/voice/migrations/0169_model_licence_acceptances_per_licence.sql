-- omnix-migration: phase=contract transactional=true
-- An acceptance is for a model's licence at a revision (migration 0168). The key now includes the licence, so a
-- catalog update that corrects a model's licence at the same revision can record the new acceptance; with the old
-- key the insert was dropped as a duplicate and the install stayed refused.

ALTER TABLE omnix_model_licence_acceptances DROP CONSTRAINT IF EXISTS omnix_model_licence_acceptances_pkey;
ALTER TABLE omnix_model_licence_acceptances
    ADD CONSTRAINT omnix_model_licence_acceptances_pkey PRIMARY KEY (workspace_id, model_id, revision, licence_id, user_id);
