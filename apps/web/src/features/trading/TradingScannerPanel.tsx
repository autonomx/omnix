import { useEffect, useMemo, useState } from 'react';
import type { CanonicalInstrument } from './tradingTypes';
import type {
  TradingScannerDefinition,
  TradingScannerMetric,
  TradingScannerOperator,
  TradingScannerResult,
  TradingScannerRun,
} from './scannerTypes';
import { tradingScannerApi } from './tradingScannerApi';

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
  const [interval, setInterval] = useState('1d');
  const [historyLimit, setHistoryLimit] = useState('100');
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');

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
      if (latest?.status === 'completed') {
        setResults(await tradingScannerApi.results(latest.run_id));
      }
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (!runs.some((run) => !terminalStatuses.has(run.status))) return;
    const timer = window.setInterval(() => void refresh(), 2_000);
    return () => window.clearInterval(timer);
  }, [runs]);

  const available = useMemo(() => instruments.slice(0, 200), [instruments]);
  const create = async () => {
    const numericThreshold = Number(threshold);
    const numericHistory = Number(historyLimit);
    if (!selectedIds.length || !Number.isFinite(numericThreshold) || !Number.isInteger(numericHistory)) {
      setStatus('error');
      return;
    }
    const scannerId = `scanner-${Date.now()}`;
    const definition: TradingScannerDefinition = {
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
        <label>Interval<select value={interval} onChange={(event) => setInterval(event.target.value)}>{['1m', '5m', '15m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}</select></label>
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
            <button type="button" onClick={() => void start(definition.scanner_id)}>Run</button>
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
      <table className="trading-scanner-results">
        <thead><tr><th>Rank</th><th>Instrument</th><th>Provider</th><th>Score</th><th>Dataset</th></tr></thead>
        <tbody>{results.map((result) => <tr key={`${result.run_id}:${result.instrument_id}`}><td>{result.rank}</td><td>{result.instrument_id}</td><td>{result.provider}</td><td>{result.score}</td><td title={result.dataset_fingerprint}>{result.dataset_fingerprint.slice(0, 8)}</td></tr>)}</tbody>
      </table>
    </section>
  );
}
