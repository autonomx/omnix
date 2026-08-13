ALTER TABLE omnix_trading_backtest_runs
    ADD COLUMN IF NOT EXISTS win_rate_percent NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE omnix_trading_backtest_runs
    ADD COLUMN IF NOT EXISTS exposure_percent NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE omnix_trading_backtest_runs
    ADD COLUMN IF NOT EXISTS artifact_storage_provider TEXT;

ALTER TABLE omnix_trading_backtest_runs
    ADD COLUMN IF NOT EXISTS artifact_storage_key TEXT;

ALTER TABLE omnix_trading_backtest_runs
    ADD COLUMN IF NOT EXISTS artifact_checksum_sha256 TEXT;

ALTER TABLE omnix_trading_backtest_runs
    ADD COLUMN IF NOT EXISTS artifact_byte_size BIGINT;

ALTER TABLE omnix_trading_backtest_runs
    DROP CONSTRAINT IF EXISTS omnix_trading_backtest_runs_metric_bounds;

ALTER TABLE omnix_trading_backtest_runs
    ADD CONSTRAINT omnix_trading_backtest_runs_metric_bounds
    CHECK (
        win_rate_percent BETWEEN 0 AND 100
        AND exposure_percent BETWEEN 0 AND 100
    );

ALTER TABLE omnix_trading_backtest_runs
    DROP CONSTRAINT IF EXISTS omnix_trading_backtest_runs_artifact_complete;

ALTER TABLE omnix_trading_backtest_runs
    ADD CONSTRAINT omnix_trading_backtest_runs_artifact_complete
    CHECK (
        (
            artifact_storage_provider IS NULL
            AND artifact_storage_key IS NULL
            AND artifact_checksum_sha256 IS NULL
            AND artifact_byte_size IS NULL
        )
        OR (
            artifact_storage_provider IS NOT NULL
            AND artifact_storage_key IS NOT NULL
            AND length(artifact_checksum_sha256) = 64
            AND artifact_byte_size > 0
        )
    );
