import { useEffect, useMemo, useState } from 'react';
import { tradingPaperApi } from './tradingPaperApi';
import { tradingStrategyApi } from './tradingStrategyApi';
import type { TradingStrategyConfig } from './tradingStrategyTypes';
import {
  tradingPaperAnalyticsApi,
  type AnalyticsNumeric,
  type PaperAnalyticsMode,
  type PaperAnalyticsOverview,
  type PaperSimulationEpoch,
} from './tradingPaperAnalyticsApi';
import './TradingPaperDashboard.css';

type DashboardTab = 'overview' | 'diagnostics' | 'execution';
type Point = { x: number; y: number; label?: string };

function numeric(value: AnalyticsNumeric | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fixed(value: AnalyticsNumeric | null | undefined, digits = 2): string {
  const parsed = numeric(value);
  return parsed === null ? '—' : parsed.toFixed(digits);
}

function signed(value: AnalyticsNumeric | null | undefined, digits = 2, suffix = ''): string {
  const parsed = numeric(value);
  if (parsed === null) return '—';
  return `${parsed > 0 ? '+' : ''}${parsed.toFixed(digits)}${suffix}`;
}

function pct(value: AnalyticsNumeric | null | undefined, digits = 1): string {
  const parsed = numeric(value);
  return parsed === null ? '—' : `${(parsed * 100).toFixed(digits)}%`;
}

function symbol(instrumentId: string): string {
  return instrumentId.split(':').at(-1)?.replace('-', '/') ?? instrumentId;
}

function shortDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function timeLabel(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function linePath(points: Point[], width: number, height: number, padding: number): { path: string; min: number; max: number } {
  if (!points.length) return { path: '', min: 0, max: 0 };
  const values = points.map((point) => point.y);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const coords = points.map((point, index) => {
    const x = padding + (points.length <= 1 ? innerWidth / 2 : index / (points.length - 1) * innerWidth);
    const y = padding + (max - point.y) / span * innerHeight;
    return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return { path: coords.join(' '), min, max };
}

function MiniLineChart({
  points,
  references = [],
  empty = 'No historical points yet.',
}: {
  points: Point[];
  references?: Array<{ value: number; label: string }>;
  empty?: string;
}) {
  const width = 760;
  const height = 220;
  const padding = 28;
  if (!points.length) return <div className="paper-dashboard-empty">{empty}</div>;
  const values = [...points.map((point) => point.y), ...references.map((reference) => reference.value)];
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const normalized = points.map((point) => ({ ...point, y: point.y }));
  const result = linePath(normalized, width, height, padding);
  const yFor = (value: number) => padding + (max - value) / span * (height - padding * 2);
  return (
    <svg className="paper-dashboard-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Time series chart">
      <line className="grid" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
      {references.map((reference) => (
        <g key={`${reference.label}-${reference.value}`}>
          <line className="reference" x1={padding} x2={width - padding} y1={yFor(reference.value)} y2={yFor(reference.value)} />
          <text className="reference-label" x={width - padding - 4} y={yFor(reference.value) - 4}>{reference.label}</text>
        </g>
      ))}
      <path className="series" d={result.path} fill="none" />
      <text className="axis-label" x={padding} y={14}>{max.toFixed(2)}</text>
      <text className="axis-label" x={padding} y={height - 6}>{min.toFixed(2)}</text>
    </svg>
  );
}

function DailyBars({ rows }: { rows: PaperAnalyticsOverview['daily_r'] }) {
  if (!rows.length) return <div className="paper-dashboard-empty">No completed strategy sessions yet.</div>;
  const max = Math.max(1, ...rows.map((row) => Math.abs(Number(row.r_result))));
  return (
    <div className="paper-dashboard-bars" role="img" aria-label="Daily R results">
      {rows.slice(-30).map((row) => {
        const value = Number(row.r_result);
        return (
          <div key={row.session_date} className="bar-column" title={`${row.session_date}: ${signed(row.r_result, 2, 'R')} · ${row.trade_count} trade(s)`}>
            <span className={value >= 0 ? 'bar positive' : 'bar negative'} style={{ height: `${Math.max(4, Math.abs(value) / max * 100)}%` }} />
            <small>{shortDate(row.session_date)}</small>
          </div>
        );
      })}
    </div>
  );
}

function Distribution({ rows }: { rows: PaperAnalyticsOverview['r_distribution'] }) {
  const max = Math.max(1, ...rows.map((row) => row.count));
  return (
    <div className="paper-dashboard-histogram" role="img" aria-label="Trade R distribution">
      {rows.map((row) => (
        <div key={row.label} title={`${row.label}: ${row.count}`}>
          <span className="hist-bar" style={{ height: `${Math.max(2, row.count / max * 100)}%` }} />
          <small>{row.label}</small>
          <strong>{row.count}</strong>
        </div>
      ))}
    </div>
  );
}

function MaeMfeScatter({ rows }: { rows: PaperAnalyticsOverview['mae_mfe'] }) {
  const width = 760;
  const height = 250;
  const padding = 34;
  if (!rows.length) return <div className="paper-dashboard-empty">MAE/MFE appears as prospective SHADOW replays and completed AUTO PAPER trades accumulate.</div>;
  const xs = rows.map((row) => Number(row.mae_r));
  const ys = rows.map((row) => Number(row.mfe_r));
  const minX = Math.min(-1, ...xs);
  const maxX = Math.max(0, ...xs);
  const minY = Math.min(0, ...ys);
  const maxY = Math.max(1.5, ...ys);
  const x = (value: number) => padding + (value - minX) / Math.max(0.0001, maxX - minX) * (width - padding * 2);
  const y = (value: number) => padding + (maxY - value) / Math.max(0.0001, maxY - minY) * (height - padding * 2);
  return (
    <svg className="paper-dashboard-chart scatter" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="MAE versus MFE scatter plot">
      <line className="reference" x1={x(-1)} x2={x(-1)} y1={padding} y2={height - padding} />
      <line className="reference" x1={padding} x2={width - padding} y1={y(0.75)} y2={y(0.75)} />
      <line className="reference target" x1={padding} x2={width - padding} y1={y(1.5)} y2={y(1.5)} />
      <text className="reference-label" x={x(-1) + 4} y={padding + 12}>−1R</text>
      <text className="reference-label" x={width - padding - 90} y={y(0.75) - 4}>+0.75R protect</text>
      <text className="reference-label" x={width - padding - 80} y={y(1.5) - 4}>+1.5R target</text>
      {rows.map((row) => (
        <circle
          key={row.trade_id}
          className={Number(row.r_result) >= 0 ? 'scatter-point winner' : 'scatter-point loser'}
          cx={x(Number(row.mae_r))}
          cy={y(Number(row.mfe_r))}
          r="5"
        >
          <title>{`${symbol(row.instrument_id)} ${row.session_date} · ${signed(row.r_result, 2, 'R')} · MAE ${signed(row.mae_r, 2, 'R')} · MFE ${signed(row.mfe_r, 2, 'R')}`}</title>
        </circle>
      ))}
    </svg>
  );
}

function Qualification({ data }: { data: NonNullable<PaperAnalyticsOverview['qualification']> }) {
  const threshold = data.thresholds;
  const items = [
    { label: 'Matched trades', value: `${data.matched_eligible_trade_count} / ${threshold.minimum_matched_trades}`, pass: data.matched_eligible_trade_count >= threshold.minimum_matched_trades },
    { label: 'Sessions', value: `${data.distinct_sessions} / ${threshold.minimum_distinct_sessions}`, pass: data.distinct_sessions >= threshold.minimum_distinct_sessions },
    { label: 'Symbols', value: `${data.distinct_symbols} / ${threshold.minimum_distinct_symbols}`, pass: data.distinct_symbols >= threshold.minimum_distinct_symbols },
    { label: 'Execution match', value: data.execution_match_rate == null ? 'N/A' : pct(data.execution_match_rate), pass: Number(data.execution_match_rate ?? 0) >= Number(threshold.minimum_execution_match_rate) },
    { label: 'Expectancy', value: data.expectancy_r == null ? 'N/A' : signed(data.expectancy_r, 3, 'R'), pass: Number(data.expectancy_r ?? Number.NEGATIVE_INFINITY) >= Number(threshold.minimum_expectancy_r) },
    { label: '90% LCB', value: data.one_sided_90_lcb_r == null ? 'N/A' : signed(data.one_sided_90_lcb_r, 3, 'R'), pass: Number(data.one_sided_90_lcb_r ?? 0) > 0 },
    { label: 'Max drawdown', value: data.max_drawdown_r == null ? 'N/A' : `${fixed(data.max_drawdown_r, 2)}R`, pass: data.max_drawdown_r != null && Number(data.max_drawdown_r) <= Number(threshold.maximum_drawdown_r) },
    { label: 'Operator review', value: data.reviewed ? 'Recorded' : 'Required', pass: data.reviewed },
  ];
  return (
    <section className="paper-qualification" data-authorized={data.auto_paper_authorized ? 'true' : 'false'}>
      <header>
        <div>
          <strong>V2 Prospective Qualification</strong>
          <small>Frozen profile · prospective evidence since {data.prospective_start}</small>
        </div>
        <span>{data.auto_paper_authorized ? 'AUTO PAPER AUTHORIZED' : 'NOT QUALIFIED'}</span>
      </header>
      <div className="qualification-grid">
        {items.map((item) => <div key={item.label} data-pass={item.pass ? 'true' : 'false'}><small>{item.label}</small><strong>{item.value}</strong><span>{item.pass ? '✓' : '✕'}</span></div>)}
      </div>
      <footer>
        <span>Profile <code>{data.current_profile_fingerprint.slice(0, 12)}</code></span>
        <span>Evidence <code>{data.evidence_fingerprint.slice(0, 12)}</code></span>
        {data.reason_codes.length ? <span>Blocking: {data.reason_codes.join(', ')}</span> : <span>Quantitative floors pass.</span>}
      </footer>
    </section>
  );
}

function Kpi({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="paper-dashboard-kpi"><small>{label}</small><strong>{value}</strong>{detail ? <span>{detail}</span> : null}</div>;
}

export function TradingPaperDashboard() {
  const [accounts, setAccounts] = useState<Array<{ account_id: string; name: string }>>([]);
  const [strategies, setStrategies] = useState<TradingStrategyConfig[]>([]);
  const [epochs, setEpochs] = useState<PaperSimulationEpoch[]>([]);
  const [accountId, setAccountId] = useState('');
  const [strategyId, setStrategyId] = useState('');
  const [epochId, setEpochId] = useState('');
  const [mode, setMode] = useState<PaperAnalyticsMode>('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [rollingWindow, setRollingWindow] = useState(20);
  const [tab, setTab] = useState<DashboardTab>('overview');
  const [data, setData] = useState<PaperAnalyticsOverview | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void Promise.all([tradingPaperApi.accounts(), tradingStrategyApi.list()]).then(([nextAccounts, nextStrategies]) => {
      if (!alive) return;
      setAccounts(nextAccounts.map((account) => ({ account_id: account.account_id, name: account.name })));
      setStrategies(nextStrategies);
      const firstAccount = nextAccounts[0]?.account_id ?? '';
      setAccountId((current) => current || firstAccount);
      if (firstAccount) {
        const firstStrategy = nextStrategies.find((strategy) => strategy.account_id === firstAccount);
        setStrategyId((current) => current || firstStrategy?.strategy_id || '');
      }
    }).catch((reason) => {
      if (!alive) return;
      setError(reason instanceof Error ? reason.message : String(reason));
      setStatus('error');
    });
    return () => { alive = false; };
  }, []);

  const accountStrategies = useMemo(
    () => strategies.filter((strategy) => strategy.account_id === accountId),
    [accountId, strategies],
  );

  useEffect(() => {
    if (!accountId) {
      setEpochs([]);
      setEpochId('');
      return;
    }
    let alive = true;
    void tradingPaperAnalyticsApi.epochs(accountId).then((nextEpochs) => {
      if (!alive) return;
      setEpochs(nextEpochs);
      const current = nextEpochs.find((epoch) => epoch.is_current) ?? nextEpochs[0];
      setEpochId((existing) => nextEpochs.some((epoch) => epoch.epoch_id === existing) ? existing : current?.epoch_id ?? '');
    }).catch((reason) => {
      if (alive) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { alive = false; };
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    let alive = true;
    setStatus('loading');
    setError(null);
    void tradingPaperAnalyticsApi.overview({
      accountId,
      strategyId: strategyId || null,
      epochId: epochId || null,
      mode,
      startDate: startDate || null,
      endDate: endDate || null,
      rollingWindow,
    }).then((overview) => {
      if (!alive) return;
      setData(overview);
      setEpochs(overview.epochs);
      setStatus('ready');
    }).catch((reason) => {
      if (!alive) return;
      setData(null);
      setError(reason instanceof Error ? reason.message : String(reason));
      setStatus('error');
    });
    return () => { alive = false; };
  }, [accountId, strategyId, epochId, mode, startDate, endDate, rollingWindow]);

  const selectAccount = (next: string) => {
    setAccountId(next);
    const firstStrategy = strategies.find((strategy) => strategy.account_id === next);
    setStrategyId(firstStrategy?.strategy_id ?? '');
    setEpochId('');
  };

  const cumulativeR = useMemo(() => {
    let total = 0;
    return (data?.daily_r ?? []).map((row, index) => {
      total += Number(row.r_result);
      return { x: index, y: total, label: row.session_date };
    });
  }, [data?.daily_r]);
  const equityPoints = useMemo(() => (data?.equity ?? []).map((row, index) => ({ x: index, y: Number(row.equity), label: row.observed_at })), [data?.equity]);
  const drawdownPoints = useMemo(() => (data?.drawdown ?? []).map((row, index) => ({ x: index, y: Number(row.drawdown), label: row.observed_at })), [data?.drawdown]);
  const rollingPoints = useMemo(() => (data?.rolling_expectancy ?? []).map((row, index) => ({ x: index, y: Number(row.expectancy_r), label: row.observed_at })), [data?.rolling_expectancy]);
  const lcbPoints = useMemo(() => (data?.rolling_expectancy ?? []).filter((row) => row.one_sided_90_lcb_r != null).map((row, index) => ({ x: index, y: Number(row.one_sided_90_lcb_r), label: row.observed_at })), [data?.rolling_expectancy]);
  const exposurePoints = useMemo(() => (data?.equity ?? []).map((row, index) => ({ x: index, y: Number(row.gross_exposure), label: row.observed_at })), [data?.equity]);
  const riskPoints = useMemo(() => (data?.equity ?? []).map((row, index) => ({ x: index, y: Number(row.risk_at_stop), label: row.observed_at })), [data?.equity]);

  if (!accounts.length && status !== 'loading') {
    return <section className="trading-paper-dashboard"><div className="paper-dashboard-empty"><strong>Paper strategy dashboard</strong><span>Create a paper account to begin collecting durable strategy evidence.</span></div></section>;
  }

  const summary = data?.summary;
  return (
    <section className="trading-paper-dashboard" aria-label="Paper strategy analytics dashboard" data-status={status}>
      <header className="paper-dashboard-header">
        <div><strong>Paper Strategy Dashboard</strong><small>Evidence, performance and SHADOW → AUTO PAPER promotion console</small></div>
        <span>{status === 'loading' ? 'Refreshing…' : status === 'error' ? 'Unavailable' : 'Durable analytics'}</span>
      </header>

      <div className="paper-dashboard-filters">
        <label><span>Account</span><select value={accountId} onChange={(event) => selectAccount(event.target.value)}>{accounts.map((account) => <option key={account.account_id} value={account.account_id}>{account.name}</option>)}</select></label>
        <label><span>Strategy</span><select value={strategyId} onChange={(event) => setStrategyId(event.target.value)}><option value="">Account only</option>{accountStrategies.map((strategy) => <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.strategy_id} · v{strategy.strategy_version}</option>)}</select></label>
        <label><span>Simulation epoch</span><select value={epochId} onChange={(event) => setEpochId(event.target.value)}><option value="">All epochs</option>{epochs.map((epoch) => <option key={epoch.epoch_id} value={epoch.epoch_id}>{epoch.is_current ? 'Current · ' : ''}Epoch {epoch.ordinal} · {shortDate(epoch.started_at)}</option>)}</select></label>
        <label><span>Mode</span><select value={mode} onChange={(event) => setMode(event.target.value as PaperAnalyticsMode)}><option value="all">SHADOW + AUTO PAPER</option><option value="shadow">Prospective SHADOW</option><option value="auto_paper">AUTO PAPER</option></select></label>
        <label><span>From</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label><span>To</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label><span>Rolling window</span><select value={rollingWindow} onChange={(event) => setRollingWindow(Number(event.target.value))}><option value={20}>20 trades</option><option value={30}>30 trades</option><option value={50}>50 trades</option></select></label>
      </div>

      {error ? <div className="paper-dashboard-error" role="status">{error}</div> : null}
      {data?.qualification ? <Qualification data={data.qualification} /> : null}

      <div className="paper-dashboard-tabs" role="tablist" aria-label="Paper dashboard section">
        <button type="button" role="tab" aria-selected={tab === 'overview'} onClick={() => setTab('overview')}>Overview</button>
        <button type="button" role="tab" aria-selected={tab === 'diagnostics'} onClick={() => setTab('diagnostics')}>Strategy diagnostics</button>
        <button type="button" role="tab" aria-selected={tab === 'execution'} onClick={() => setTab('execution')}>Execution &amp; risk</button>
      </div>

      {data ? (
        <>
          <div className="paper-dashboard-kpis">
            <Kpi label="Trades" value={String(summary?.trade_count ?? 0)} detail={`${summary?.wins ?? 0}W / ${summary?.losses ?? 0}L`} />
            <Kpi label="Expectancy" value={signed(summary?.expectancy_r, 3, 'R')} detail={`Total ${signed(summary?.total_r, 2, 'R')}`} />
            <Kpi label="Win rate" value={pct(summary?.win_rate)} />
            <Kpi label="Profit factor" value={fixed(summary?.profit_factor, 2)} />
            <Kpi label="Max drawdown" value={summary?.max_drawdown_r == null ? '—' : `${fixed(summary.max_drawdown_r, 2)}R`} />
            <Kpi label="Avg MAE / MFE" value={`${fixed(summary?.average_mae_r, 2)}R / ${fixed(summary?.average_mfe_r, 2)}R`} />
            <Kpi label="Archived strategies" value={String(data.archived_strategy_count)} detail="Audit history retained" />
          </div>

          {tab === 'overview' ? (
            <div className="paper-dashboard-grid">
              <article className="wide"><header><div><strong>{cumulativeR.length ? 'Cumulative R' : 'Account equity'}</strong><small>{cumulativeR.length ? 'Strategy-normalized performance' : 'Mark-to-market paper account history'}</small></div></header><MiniLineChart points={cumulativeR.length ? cumulativeR : equityPoints} references={cumulativeR.length ? [{ value: 0, label: '0R' }] : []} /></article>
              <article className="wide"><header><div><strong>Underwater drawdown</strong><small>{data.drawdown[0]?.unit === 'R' ? 'Peak-to-trough in R' : 'Peak-to-trough account equity %'}</small></div></header><MiniLineChart points={drawdownPoints} references={[{ value: 0, label: 'peak' }]} /></article>
              <article><header><div><strong>Daily R</strong><small>Click-free session consistency view</small></div></header><DailyBars rows={data.daily_r} /></article>
              <article><header><div><strong>Rolling expectancy</strong><small>{rollingWindow}-trade window · +0.20R V2 threshold</small></div></header><MiniLineChart points={rollingPoints} references={[{ value: 0, label: '0R' }, { value: 0.2, label: '+0.20R qualify' }]} /></article>
              <article><header><div><strong>R distribution</strong><small>Outcome shape matters more than win rate alone</small></div></header><Distribution rows={data.r_distribution} /></article>
              <article><header><div><strong>Rolling 90% lower bound</strong><small>Evidence reliability, not just point estimate</small></div></header><MiniLineChart points={lcbPoints} references={[{ value: 0, label: 'must stay > 0R' }]} /></article>
              <article className="wide"><header><div><strong>MAE vs MFE</strong><small>Validate stop, protection and +1.5R target geometry</small></div></header><MaeMfeScatter rows={data.mae_mfe} /></article>
              <article className="wide"><header><div><strong>Candidate lifecycle</strong><small>One strategy/profile/session/universe/instrument lifecycle — not raw event counts</small></div></header><div className="paper-funnel">{data.funnel.map((stage, index) => <div key={stage.stage}><span>{stage.stage}</span><strong>{stage.count}</strong><small>{index === 0 ? 'Captured lifecycle' : stage.conversion_from_previous == null ? '—' : `${(Number(stage.conversion_from_previous) * 100).toFixed(0)}% from prior`}</small>{stage.dominant_drop_reason ? <em>{stage.dominant_drop_count} stopped: {stage.dominant_drop_reason}</em> : null}</div>)}</div></article>
            </div>
          ) : null}

          {tab === 'diagnostics' ? (
            <div className="paper-dashboard-grid">
              <article className="wide"><header><div><strong>Factor studies</strong><small>Prospective/AUTO PAPER outcome buckets from persisted setup features</small></div></header>{data.factors.length ? <div className="paper-factor-studies">{data.factors.map((study) => <section key={study.factor}><strong>{study.factor}</strong><table><thead><tr><th>Bucket</th><th>N</th><th>Expectancy</th><th>Win rate</th></tr></thead><tbody>{study.buckets.map((bucket) => <tr key={bucket.label}><td>{bucket.label}</td><td>{bucket.count}</td><td className={Number(bucket.expectancy_r) >= 0 ? 'positive' : 'negative'}>{signed(bucket.expectancy_r, 3, 'R')}</td><td>{pct(bucket.win_rate)}</td></tr>)}</tbody></table></section>)}</div> : <div className="paper-dashboard-empty">Factor buckets populate as completed AUTO PAPER trades retain setup features such as gap, RVOL, float, spread, pullback depth and quality score.</div>}</article>
              <article className="wide"><header><div><strong>Recent strategy trades</strong><small>Canonical round trips and prospective SHADOW replay outcomes</small></div></header><div className="paper-trades-table"><table><thead><tr><th>Session</th><th>Symbol</th><th>Mode</th><th>Result</th><th>MAE</th><th>MFE</th><th>Exit</th><th>Entry → exit</th></tr></thead><tbody>{data.recent_trades.map((trade) => <tr key={`${trade.source}-${trade.trade_id}`}><td>{trade.session_date}</td><td><strong>{symbol(trade.instrument_id)}</strong></td><td>{trade.source === 'shadow_replay' ? 'SHADOW replay' : 'AUTO PAPER'}</td><td className={Number(trade.r_result) >= 0 ? 'positive' : 'negative'}>{signed(trade.r_result, 3, 'R')}</td><td>{trade.mae_r == null ? '—' : signed(trade.mae_r, 2, 'R')}</td><td>{trade.mfe_r == null ? '—' : signed(trade.mfe_r, 2, 'R')}</td><td>{trade.exit_reason ?? '—'}</td><td>{timeLabel(trade.entry_time)} → {timeLabel(trade.exit_time)}</td></tr>)}{!data.recent_trades.length ? <tr><td colSpan={8}>No completed trades in this filter.</td></tr> : null}</tbody></table></div></article>
            </div>
          ) : null}

          {tab === 'execution' ? (
            <div className="paper-dashboard-grid">
              <article className="wide"><header><div><strong>Expected → observed → realized</strong><small>Separate signal deterioration from fill slippage and total implementation shortfall</small></div></header><div className="paper-execution-kpis"><Kpi label="AUTO PAPER trades" value={String(data.execution.trade_count)} /><Kpi label="Signal → executable" value={data.execution.average_signal_to_executable_bps == null ? '—' : `${fixed(data.execution.average_signal_to_executable_bps, 1)} bps`} /><Kpi label="Execution → fill" value={data.execution.average_fill_slippage_bps == null ? '—' : `${fixed(data.execution.average_fill_slippage_bps, 1)} bps`} /><Kpi label="Total shortfall" value={data.execution.average_implementation_shortfall_bps == null ? '—' : `${fixed(data.execution.average_implementation_shortfall_bps, 1)} bps`} /></div></article>
              <article><header><div><strong>Gross exposure</strong><small>Mark-to-market notional over time</small></div></header><MiniLineChart points={exposurePoints} /></article>
              <article><header><div><strong>Risk at stop</strong><small>Persisted protection risk over time</small></div></header><MiniLineChart points={riskPoints} /></article>
              <article className="wide"><header><div><strong>Simulation history</strong><small>Reset starts a new immutable epoch instead of erasing prior evidence</small></div></header><div className="paper-epochs">{epochs.map((epoch) => <div key={epoch.epoch_id} data-current={epoch.is_current ? 'true' : 'false'}><strong>Epoch {epoch.ordinal}</strong><span>{epoch.is_current ? 'CURRENT' : epoch.end_reason?.replaceAll('_', ' ') ?? 'closed'}</span><small>Initial ${Number(epoch.initial_cash).toLocaleString()} · {timeLabel(epoch.started_at)}{epoch.ended_at ? ` → ${timeLabel(epoch.ended_at)}` : ''}</small></div>)}</div></article>
            </div>
          ) : null}
        </>
      ) : <div className="paper-dashboard-empty">{status === 'loading' ? 'Loading durable paper analytics…' : 'No analytics available.'}</div>}
    </section>
  );
}
