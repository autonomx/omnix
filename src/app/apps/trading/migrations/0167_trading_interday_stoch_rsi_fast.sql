-- omnix-migration: phase=data transactional=true
-- Attach a shorter-warm-up 5m Stoch RSI variant as a live SHADOW child of the
-- interday group. The evaluator reads only the current regular session, so
-- the 14/14/3/3 children cannot arm a setup before 12:10 ET (32 finished
-- five-minute bars). This child uses 9/9/3/3 (22 bars, first signal 11:20 ET)
-- and is otherwise cloned from the workspace's ``stoch-rsi-5min`` child: same
-- account, universe filters, thresholds and risk, with its own daily
-- auto-archived universe.
--
-- Data only: every field already exists, so older application code reads the
-- row unchanged.

INSERT INTO omnix_trading_strategy_configs (
    workspace_id, strategy_id, parent_strategy_id, account_id, owner_user_id,
    strategy_kind, strategy_version, mode, active_universe_id,
    config, risk, enabled
)
SELECT source.workspace_id,
       'stoch-rsi-5min-fast',
       'interday-trading-strategy-shadow',
       source.account_id,
       source.owner_user_id,
       source.strategy_kind,
       source.strategy_version,
       'shadow',
       NULL,
       source.config
           || '{"rsi_period": 9, "stochastic_period": 9, "k_smoothing_period": 3, "d_smoothing_period": 3, "trade_selection": "sequential", "auto_archive_daily_universe": true}'::jsonb,
       source.risk,
       TRUE
  FROM omnix_trading_strategy_configs AS source
 WHERE source.strategy_id = 'stoch-rsi-5min'
   AND source.strategy_kind = 'stoch_rsi_5m_v1'
   AND source.archived_at IS NULL
   AND EXISTS (
       SELECT 1
         FROM omnix_trading_strategy_configs AS parent
        WHERE parent.workspace_id = source.workspace_id
          AND parent.strategy_id = 'interday-trading-strategy-shadow'
   )
ON CONFLICT (workspace_id, strategy_id) DO NOTHING;
