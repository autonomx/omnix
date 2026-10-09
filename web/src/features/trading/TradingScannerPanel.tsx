import { useEffect, useMemo, useRef, useState } from 'react';
import { AUTO_REFRESH_OPTIONS, resultChanges, useScannerAutoRefresh, type AutoRefresh } from './scannerAutoRefresh';
import type { CanonicalInstrument } from './tradingTypes';
import type {
  TradingScannerDefinition,
  TradingScannerDefinitionInput,
  TradingScannerMetric,
  TradingScannerOperator,
  TradingScannerResult,
  TradingScannerRun,
} from './scannerTypes';
import { tradingScannerApi } from './tradingScannerApi';
import { POLL_INTERVALS_MS, startPolling } from '../../shared/timers';

const terminalStatuses = new Set(['completed', 'failed', 'cancelled', 'timed_out']);

export function TradingScannerPanel({ instruments }: { instruments: CanonicalInstrument[] }) {
  const [definitions, setDefinitions] = useState<TradingScannerDefinition[]>([]);
  const [runs, setRuns] = useState<TradingScannerRun[]>([]);
  const [results, setResults] = useState<TradingScannerResult[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [name, setName] = useState('Momentum scan');
  const [metric, setMetric] = useState<TradingScannerMetric>('percent_change');
  const [operator, setOperator] = useState<TradingScannerOperator>('gte');
  const [threshold, setThreshold] = useState('1');
  const [interval, setScanInterval] = useState('1d');
  const [historyLimit, setHistoryLimit] = useState('100');
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');
  const [autoRefresh, setAutoRefresh] = useState<AutoRefresh | null>(null);
  const [changes, setChanges] = useState<ReturnType<typeof resultChanges>>({ added: new Set(), removed: [] });
  // The results shown before the latest run, and which run they came from, to say what changed.
  const shown = useRef<{ runId: string | null; scannerId: string | null; results: TradingScannerResult[] | null }>({ runId: null, scannerId: null, results: null });

  const refresh = async () => {
    try {
      const [nextDefinitions, nextRuns] = await Promise.all([
        tradingScannerApi.definitions(),
        tradingScannerApi.runs(),
      ]);
      setDefinitions(nextDefinitions);
      setRuns(nextRuns);
      setStatus('ready');
      const latest = nextRuns[0];
      if (latest?.status === 'completed' && latest.run_id !== shown.current.runId) {
        // Claimed before the await: an overlapping refresh does not diff the run against itself.
        const previous = shown.current;
        shown.current = { ...previous, runId: latest.run_id };
        const next = await tradingScannerApi.results(latest.run_id);
        // Changes only compare runs of the same screen.
        setChanges(previous.scannerId === latest.scanner_id ? resultChanges(previous.results, next) : resultChanges(null, next));
        shown.current = { runId: latest.run_id, scannerId: latest.scanner_id, results: next };
        setResults(next);
      }
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (!runs.some((run) => !terminalStatuses.has(run.status))) return;
    return startPolling(refresh, POLL_INTERVALS_MS.scanner);
  }, [runs]);

  // Auto-refresh (TVP-9.2): a new run only when none of the screen's runs is still working.
  const working = (scannerId: string) => runs.some((run) => run.scanner_id === scannerId && !terminalStatuses.has(run.status));
  useScannerAutoRefresh(autoRefresh, working, async (scannerId) => {
    await tradingScannerApi.start(scannerId);
    await refresh();
  }, () => {
    setAutoRefresh(null);
    setStatus('error');
  });

  const available = useMemo(() => instruments.slice(0, 200), [instruments]);
  const create = async () => {
    const numericThreshold = Number(threshold);
    const numericHistory = Number(historyLimit);
    if (!selectedIds.length || !Number.isFinite(numericThreshold) || !Number.isInteger(numericHistory)) {
      setStatus('error');
      return;
    }
    const scannerId = `scanner-${Date.now()}`;
    const definition: TradingScannerDefinitionInput = {
      scanner_id: scannerId,
      name,
      instrument_ids: selectedIds,
      binding_ids: {},
      interval,
      history_limit: numericHistory,
      rules: [{
        rule_id: 'primary',
        metric,
        operator,
        threshold,
        period: 14,
        lookback_bars: 1,
      }],
      max_concurrency: 4,
      request_timeout_seconds: 10,
      run_timeout_seconds: 120,
      formula_version: 'omnix-indicators-v2',
      enabled: true,
      revision: 1,
    };
    setStatus('saving');
    try {
      const saved = await tradingScannerApi.create(definition);
      await tradingScannerApi.start(saved.scanner_id);
      await refresh();
    } catch {
      setStatus('error');
    }
  };

  const start = async (scannerId: string) => {
    setStatus('saving');
    try {
      await tradingScannerApi.start(scannerId);
      await refresh();
    } catch {
      setStatus('error');
    }
  };

  return (
    <section className="trading-scanner-panel" aria-label="Bounded market scanner" data-status={status}>
      <header><strong>Bounded scanner</strong><span>{status}</span></header>
      <p>Allowlist only. Maximum 200 instruments, 500 bars, 8 concurrent requests, and 5-minute total runtime.</p>
      <div className="trading-scanner-form">
        <label>Name<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Metric<select value={metric} onChange={(event) => setMetric(event.target.value as TradingScannerMetric)}>{['close', 'percent_change', 'volume', 'sma', 'ema', 'rsi', 'atr'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Operator<select value={operator} onChange={(event) => setOperator(event.target.value as TradingScannerOperator)}>{['gt', 'gte', 'lt', 'lte'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Threshold<input inputMode="decimal" value={threshold} onChange={(event) => setThreshold(event.target.value)} /></label>
        <label>Interval<select value={interval} onChange={(event) => setScanInterval(event.target.value)}>{['1m', '5m', '15m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>History bars<input inputMode="numeric" value={historyLimit} onChange={(event) => setHistoryLimit(event.target.value)} /></label>
      </div>
      <fieldset className="trading-scanner-universe">
        <legend>Instrument allowlist ({selectedIds.length}/200)</legend>
        {available.map((instrument) => (
          <label key={instrument.instrument_id}>
            <input
              type="checkbox"
              checked={selectedIds.includes(instrument.instrument_id)}
              onChange={(event) => setSelectedIds((current) => event.target.checked
                ? [...current, instrument.instrument_id].slice(0, 200)
                : current.filter((item) => item !== instrument.instrument_id))}
            />
            {instrument.display_symbol}
          </label>
        ))}
      </fieldset>
      <button type="button" disabled={!selectedIds.length || status === 'saving'} onClick={() => void create()}>Save and run scanner</button>
      <ul className="trading-scanner-definitions">
        {definitions.map((definition) => (
          <li key={definition.scanner_id}>
            <div><strong>{definition.name}</strong><small>{definition.instrument_ids.length} instruments · {definition.interval} · revision {definition.revision}</small></div>
            <button type="button" disabled={working(definition.scanner_id)} onClick={() => void start(definition.scanner_id)}>Run</button>
            <select
              aria-label={`Auto-refresh ${definition.name}`}
              value={autoRefresh?.scannerId === definition.scanner_id ? autoRefresh.everyMs : 0}
              onChange={(event) => {
                const everyMs = Number(event.target.value);
                setAutoRefresh(everyMs > 0 ? { scannerId: definition.scanner_id, everyMs } : null);
                if (everyMs > 0 && !working(definition.scanner_id)) void start(definition.scanner_id);
              }}
            >
              {AUTO_REFRESH_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </li>
        ))}
      </ul>
      <ul className="trading-scanner-runs">
        {runs.slice(0, 10).map((run) => (
          <li key={run.run_id}>
            <div><strong>{run.status}</strong><small>{run.completed_count}/{run.universe_count} · {run.matched_count} matches</small></div>
            {!terminalStatuses.has(run.status) ? <button type="button" onClick={() => void tradingScannerApi.cancel(run.run_id).then(refresh)}>Cancel</button> : null}
          </li>
        ))}
      </ul>
      {changes.added.size > 0 || changes.removed.length > 0 ? (
        <p className="trading-scanner-changes" role="status">
          Since the previous run: {changes.added.size} new, {changes.removed.length} dropped{changes.removed.length > 0 ? ` (${changes.removed.join(', ')})` : ''}.
        </p>
      ) : null}
      <table className="trading-scanner-results">
        <thead><tr><th>Rank</th><th>Instrument</th><th>Provider</th><th>Score</th><th>Dataset</th></tr></thead>
        <tbody>{results.map((result) => <tr key={`${result.run_id}:${result.instrument_id}`} className={changes.added.has(result.instrument_id) ? 'is-new' : undefined} title={changes.added.has(result.instrument_id) ? 'New since the previous run' : undefined}><td>{result.rank}</td><td>{result.instrument_id}</td><td>{result.provider}</td><td>{result.score}</td><td title={result.dataset_fingerprint}>{result.dataset_fingerprint.slice(0, 8)}</td></tr>)}</tbody>
      </table>
    </section>
  );
}
