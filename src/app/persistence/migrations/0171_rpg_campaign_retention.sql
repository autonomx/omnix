-- omnix-migration: phase=expand transactional=true
-- RQ-8.10: a deleted (archived) campaign is removed with everything of its own
-- after 30 days, and a campaign past 5,000 revisions keeps its newest 1,000
-- turns behind a pinned snapshot; app.apps.rpg.declarations does both.
INSERT INTO omnix_retention_policies (record_type, retention_days, terminal_only, enabled, metadata)
VALUES ('rpg_archived_campaigns', 30, FALSE, TRUE,
        '{"deletes": "archived campaigns and every row that cascades from them"}'::jsonb),
       ('rpg_turn_compaction', 1, FALSE, TRUE,
        '{"keeps": "every turn of campaigns up to 5000 revisions; the newest 1000 beyond that"}'::jsonb)
ON CONFLICT (record_type) DO NOTHING;
