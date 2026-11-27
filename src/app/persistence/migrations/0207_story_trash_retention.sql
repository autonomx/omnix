-- omnix-migration: phase=expand transactional=true
-- ST-1.5: a trashed story project (omnix_story_projects, 0203) is purged after 30 days, with
-- everything that cascades from it; app.apps.story.declarations deletes it. The policy row is
-- the platform's table, so it is written here, not in the story module's migration (AL016).
INSERT INTO omnix_retention_policies (record_type, retention_days, terminal_only, enabled, metadata)
VALUES ('story_trashed_projects', 30, FALSE, TRUE,
        '{"deletes": "trashed story projects and every row that cascades from them"}'::jsonb)
ON CONFLICT (record_type) DO NOTHING;
