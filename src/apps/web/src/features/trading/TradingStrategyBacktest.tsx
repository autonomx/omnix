import { useEffect, useMemo, useState } from 'react';
import { tradingStrategyApi } from './tradingStrategyApi';
import type { StrategyRangeBacktestResult, TradingStrategyConfig } from './tradingStrategyTypes';

function isoDate(offsetDays = 0): string {
  const value = new Date();
  value.setDate(value.getDate() + offsetDays);
  return value.toISOString().slice(0, 10);
}

function numeric(value: string | number | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: string | number | null | undefined): string {
  return numeric(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
}

function ratio(value: string | number | null | undefined, digits = 2): string {
  return numeric(value).toFixed(digits);
}

export function TradingStrategyBacktest({ strategy }: { strategy: TradingStrategyConfig }) {
  const [startDate, setStartDate] = useState(() => isoDate(-14));
  const [endDate, setEndDate] = useState(() => isoDate(0));
  const [initialCash, setInitialCash] = useState('100000');
  const [spreadBps, setSpreadBps] = useState('40');
  const [maxHoldMinutes, setMaxHoldMinutes] = useState('90');
  const [cutoffEt, setCutoffEt] = useState(strategy.config.entry_start_et.slice(0, 5));
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState('Backtest the saved strategy configuration across a date range.');
  const [result, setResult] = useState<StrategyRangeBacktestResult | null>(null);

  useEffect(() => {
    setCutoffEt(strategy.config.entry_start_et.slice(0, 5));
    setResult(null);
    setNotice('Backtest the saved strategy configuration across a date range.');
  }, [strategy.strategy_id, strategy.revision]);

  const run = async () => {
    if (!startDate || !endDate) {
      setNotice('Choose both a start and end date.');
      return;
    }
    if (endDate < startDate) {
      setNotice('End date must be on or after start date.');
      return;
    }
    setRunning(true);
    setResult(null);
    setNotice('Running strategy-specific daily universe backtest…');
    try {
      const next = await tradingStrategyApi.backtestRange(strategy.strategy_id, {
        start_date: startDate,
        end_date: endDate,
        initial_cash: initialCash,
        assumed_spread_bps: spreadBps,
        max_hold_minutes: Number(maxHoldMinutes),
        universe_cutoff_et: cutoffEt ? `${cutoffEt}:00` : null,
        max_sessions: 60,
      });
      setResult(next);
      const incomplete = next.missing_universe_sessions + next.data_unavailable_sessions + next.error_sessions;
      setNotice(incomplete
        ? `Backtest completed with ${next.covered_sessions}/${next.requested_trading_sessions} sessions covered. Missing/unavailable days are shown explicitly and are not treated as no-trade days.`
        : `Backtest completed across all ${next.covered_sessions} requested trading sessions.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setRunning(false);
    }
  };

  const coverageTone = useMemo(() => {
    if (!result) return 'idle';
    return result.covered_sessions === result.requested_trading_sessions ? 'complete' : 'attention';
  }, [result]);

  return (
    <section className="strategy-range-backtest" aria-label="Strategy-specific backtest">
      <header>
        <div>
          <strong>Backtest this strategy</strong>
          <small>Replay the saved {strategy.strategy_kind} config and risk profile day by day, including daily candidate selection and portfolio limits.</small>
        </div>
        <span>{strategy.config.structure_interval} structure / {strategy.config.execution_interval} execution</span>
      </header>

      <div className="strategy-backtest-controls">
        <label><span>Start date</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label><span>End date</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label><span>Initial cash</span><input type="number" min="1" step="1000" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} /></label>
        <label><span>Assumed spread<small>bps</small></span><input type="number" min="0" step="5" value={spreadBps} onChange={(event) => setSpreadBps(event.target.value)} /></label>
        <label><span>Max hold<small>minutes</small></span><input type="number" min="1" max="390" value={maxHoldMinutes} onChange={(event) => setMaxHoldMinutes(event.target.value)} /></label>
        <label><span>Universe cutoff ET<small>only evidence frozen by this time is eligible</small></span><input type="time" value={cutoffEt} onChange={(event) => setCutoffEt(event.target.value)} /></label>
        <button type="button" className="primary" disabled={running} onClick={() => void run()}>{running ? 'Running backtest…' : 'Run strategy backtest'}</button>
      </div>

      <div className="strategy-backtest-causality-note">
        <strong>Point-in-time rule</strong>
        <span>The backtest does not reconstruct a past Yahoo “top gainers” screen using today’s knowledge. Each day must have an immutable gapper/research universe that Omnix actually froze by the configured cutoff. A later human/LLM “selected” universe is excluded so the deterministic strategy performs its own historical selection.</span>
      </div>
      <p className="strategy-backtest-notice" role="status">{notice}</p>

      {result ? (
        <>
          <div className="strategy-backtest-summary" data-coverage={coverageTone}>
            <article><small>Coverage</small><strong>{result.covered_sessions}/{result.requested_trading_sessions}</strong><span>{result.missing_universe_sessions} missing universe · {result.data_unavailable_sessions} unavailable data</span></article>
            <article><small>Ending equity</small><strong>{money(result.ending_cash)}</strong><span>{money(result.pnl)} · {ratio(result.return_pct)}%</span></article>
            <article><small>Trades</small><strong>{result.trade_count}</strong><span>{result.win_count} wins · {result.loss_count} losses · {result.trigger_count} triggers</span></article>
            <article><small>Expectancy</small><strong>{ratio(result.expectancy_r)}R</strong><span>{result.candidate_count} point-in-time candidates evaluated</span></article>
          </div>

          <div className="strategy-backtest-days-wrap">
            <table className="strategy-backtest-days">
              <thead><tr><th>Date</th><th>Status</th><th>Universe</th><th>Candidates</th><th>Triggers</th><th>Trades</th><th>P&amp;L</th><th>Ending cash</th></tr></thead>
              <tbody>
                {result.days.map((day) => (
                  <tr key={day.session_date} data-status={day.status} title={day.detail ?? undefined}>
                    <td>{day.session_date}</td>
                    <td><strong>{day.status.replaceAll('_', ' ')}</strong>{day.detail ? <small>{day.detail}</small> : null}</td>
                    <td>{day.universe_id ?? '—'}</td>
                    <td>{day.candidate_count}</td>
                    <td>{day.trigger_count}</td>
                    <td>{day.trade_count}</td>
                    <td>{money(day.pnl)}</td>
                    <td>{money(day.ending_cash)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <details className="strategy-backtest-trades">
            <summary>Trade-by-trade detail</summary>
            <div>
              {result.days.flatMap((day) => (day.result?.trades ?? []).map((trade, index) => (
                <article key={`${day.session_date}-${trade.instrument_id}-${trade.entry_time}-${index}`}>
                  <header><strong>{trade.instrument_id.split(':').at(-1) ?? trade.instrument_id}</strong><span>{day.session_date}</span><b>{ratio(trade.r_multiple)}R</b></header>
                  <small>score {trade.quality_score}/10 · entry {money(trade.entry_price)} · exit {money(trade.exit_price)} · {trade.exit_reason} · qty {ratio(trade.entry_fill_quantity, 0)}</small>
                </article>
              )))}
              {!result.trade_count ? <p>No trades were executed in covered sessions.</p> : null}
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}
