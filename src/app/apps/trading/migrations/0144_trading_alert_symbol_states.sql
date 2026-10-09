-- omnix-migration: phase=expand transactional=true
-- TVP-1.7: watchlist alerts.
--
-- A watchlist alert is an alert whose instrument_id is 'watchlist:<record id>': one definition evaluated on every
-- symbol of that watchlist, read at evaluation time. What an ordinary alert keeps on its own row (the last observed
-- price and value, the last trigger, whether a 'once' alert has fired) a watchlist alert keeps per symbol here.
-- A row belongs to the alert's definition and revision it was written under; a newer one starts the symbol afresh.

CREATE TABLE IF NOT EXISTS omnix_trading_alert_symbol_states (
    workspace_id TEXT NOT NULL,
    alert_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    alert_revision BIGINT NOT NULL CHECK (alert_revision >= 1),
    definition_revision BIGINT NOT NULL CHECK (definition_revision >= 1),
    last_observed_price NUMERIC,
    last_observed_value NUMERIC,
    last_triggered_at TIMESTAMPTZ,
    -- A 'once' alert stops for a symbol once it has fired there; editing the alert re-arms it.
    fired_once BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, alert_id, instrument_id),
    FOREIGN KEY (workspace_id, alert_id)
        REFERENCES omnix_trading_alerts(workspace_id, alert_id)
        ON DELETE CASCADE
);
