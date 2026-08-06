CREATE TABLE IF NOT EXISTS omnix_trading_alerts (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    alert_id TEXT NOT NULL,
    owner_user_id TEXT REFERENCES omnix_users(id) ON DELETE SET NULL,
    instrument_id TEXT NOT NULL,
    binding_id TEXT,
    condition_type TEXT NOT NULL CHECK (condition_type IN ('price_above', 'price_below')),
    threshold NUMERIC NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    cooldown_seconds INTEGER NOT NULL DEFAULT 0 CHECK (cooldown_seconds >= 0),
    last_observed_price NUMERIC,
    last_triggered_at TIMESTAMPTZ,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, alert_id)
);

CREATE INDEX IF NOT EXISTS idx_omnix_trading_alerts_evaluation
    ON omnix_trading_alerts (workspace_id, instrument_id, enabled, updated_at DESC);

CREATE TABLE IF NOT EXISTS omnix_trading_alert_triggers (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    trigger_id TEXT NOT NULL,
    alert_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    observed_price NUMERIC NOT NULL,
    threshold NUMERIC NOT NULL,
    condition_type TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, trigger_id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, alert_id)
        REFERENCES omnix_trading_alerts(workspace_id, alert_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_omnix_trading_alert_triggers_recent
    ON omnix_trading_alert_triggers (workspace_id, observed_at DESC, alert_id);
