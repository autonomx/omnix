ALTER TABLE omnix_trading_backtest_trades
    ADD COLUMN IF NOT EXISTS signal_bar_index INTEGER;

ALTER TABLE omnix_trading_backtest_trades
    ADD COLUMN IF NOT EXISTS fill_bar_index INTEGER;

UPDATE omnix_trading_backtest_trades
   SET signal_bar_index = COALESCE(signal_bar_index, trade_index * 2),
       fill_bar_index = COALESCE(fill_bar_index, trade_index * 2 + 1)
 WHERE signal_bar_index IS NULL OR fill_bar_index IS NULL;

ALTER TABLE omnix_trading_backtest_trades
    ALTER COLUMN signal_bar_index SET NOT NULL;

ALTER TABLE omnix_trading_backtest_trades
    ALTER COLUMN fill_bar_index SET NOT NULL;

ALTER TABLE omnix_trading_backtest_trades
    DROP CONSTRAINT IF EXISTS omnix_trading_backtest_trades_next_bar_check;

ALTER TABLE omnix_trading_backtest_trades
    ADD CONSTRAINT omnix_trading_backtest_trades_next_bar_check
    CHECK (signal_bar_index >= 0 AND fill_bar_index = signal_bar_index + 1);
