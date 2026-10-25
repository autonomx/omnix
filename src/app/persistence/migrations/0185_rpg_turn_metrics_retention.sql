-- omnix-migration: phase=expand transactional=true
-- RQ-8.4: a campaign's turn metrics (omnix_rpg_turn_metrics, 0184) are kept 90 days;
-- app.apps.rpg.declarations deletes the older rows. The policy row is the platform's
-- table, so it is written here, not in the RPG module's migration (AL016).
INSERT INTO omnix_retention_policies (record_type, retention_days, terminal_only)
VALUES ('rpg_turn_metrics', 90, FALSE)
ON CONFLICT (record_type) DO NOTHING;
