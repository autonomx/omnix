-- omnix-migration: phase=expand transactional=true
-- RQ-8.4 (docs/RPG_PRODUCTION_ROADMAP_2026-10-23.md): one row per turn the turn route ran, for the operations view:
-- its class (the mechanic the pipeline planned, or the turn's kind), whether it failed and how, how many optional
-- stages degraded, how long it took, and the model calls it made. Never game state; kept 90 days.
CREATE TABLE IF NOT EXISTS omnix_rpg_turn_metrics (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    metric_id BIGSERIAL NOT NULL,
    campaign_id TEXT NOT NULL CHECK (length(campaign_id) BETWEEN 1 AND 300),
    submission_id TEXT NOT NULL DEFAULT '' CHECK (length(submission_id) <= 300),
    turn_class TEXT NOT NULL CHECK (length(turn_class) BETWEEN 1 AND 100),
    ok BOOLEAN NOT NULL,
    error TEXT NOT NULL DEFAULT '' CHECK (length(error) <= 200),
    degraded_stages INTEGER NOT NULL DEFAULT 0 CHECK (degraded_stages >= 0),
    complete_ms DOUBLE PRECISION CHECK (complete_ms IS NULL OR complete_ms >= 0),
    model_calls INTEGER NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    model_failures INTEGER NOT NULL DEFAULT 0 CHECK (model_failures >= 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, metric_id)
);

CREATE INDEX IF NOT EXISTS idx_omnix_rpg_turn_metrics_recent
    ON omnix_rpg_turn_metrics (workspace_id, recorded_at DESC);

-- Row-level security, like every other table with workspace_id (WP-4.4).
ALTER TABLE omnix_rpg_turn_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_rpg_turn_metrics FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON omnix_rpg_turn_metrics;
CREATE POLICY tenant_isolation ON omnix_rpg_turn_metrics
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

INSERT INTO omnix_retention_policies (record_type, retention_days, terminal_only)
VALUES ('rpg_turn_metrics', 90, FALSE)
ON CONFLICT (record_type) DO NOTHING;
