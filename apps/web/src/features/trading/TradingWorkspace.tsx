import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { TradingChartPanel } from './TradingChartPanel';
import { tradingApi } from './tradingApi';
import type { TradingChartType } from './chart/chartAdapter';
import './TradingWorkspace.css';

export function TradingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [focusMode, setFocusMode] = useState(false);
  const [instrumentId, setInstrumentId] = useState('');
  const [interval, setInterval] = useState('1m');
  const [chartType, setChartType] = useState<TradingChartType>('candlestick');
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });

  useEffect(() => {
    if (!instrumentId && instruments.data?.[0]) setInstrumentId(instruments.data[0].instrument_id);
  }, [instrumentId, instruments.data]);

  return (
    <main className={`trading-workspace${focusMode ? ' trading-focus-mode' : ''}`} aria-labelledby="trading-title">
      <header className="trading-workspace-header">
        <div>
          <p className="eyebrow">Native Omnix module</p>
          <h2 id="trading-title">{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <button type="button" onClick={() => setFocusMode((value) => !value)} aria-pressed={focusMode}>
          {focusMode ? 'Exit focus mode' : 'Focus mode'}
        </button>
      </header>

      <section className="trading-toolbar" aria-label="Trading toolbar">
        <label>
          Instrument
          <select aria-label="Trading instrument" value={instrumentId} onChange={(event) => setInstrumentId(event.target.value)}>
            {(instruments.data ?? []).map((instrument) => (
              <option key={instrument.instrument_id} value={instrument.instrument_id}>
                {instrument.display_symbol} · {instrument.venue}
              </option>
            ))}
          </select>
        </label>
        <label>
          Timeframe
          <select aria-label="Trading timeframe" value={interval} onChange={(event) => setInterval(event.target.value)}>
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Chart
          <select aria-label="Trading chart type" value={chartType} onChange={(event) => setChartType(event.target.value as TradingChartType)}>
            <option value="candlestick">Candlestick</option>
            <option value="line">Line</option>
          </select>
        </label>
        <button type="button">Indicators</button>
        <button type="button">Layout: 1 chart</button>
        <span className="trading-provider-status" data-status={providers.data?.[0]?.status ?? 'unavailable'}>
          {providers.isLoading ? 'Loading data provider…' : `${providers.data?.[0]?.display_name ?? 'Provider unavailable'} · ${providers.data?.[0]?.status ?? 'unavailable'}`}
        </span>
      </section>

      <div className="trading-body">
        <aside className="trading-tools" aria-label="Chart drawing tools">
          {['Cursor', 'Crosshair', 'Trend line', 'Horizontal line', 'Measure'].map((tool) => (
            <button key={tool} type="button" title={tool} aria-label={tool}>{tool.slice(0, 2)}</button>
          ))}
        </aside>
        <section className="trading-chart-shell" aria-label="Trading chart workspace">
          {instrumentId ? <TradingChartPanel instrumentId={instrumentId} interval={interval} chartType={chartType} /> : (
            <div className="trading-chart-empty"><strong>Loading instrument catalog…</strong></div>
          )}
        </section>
        <aside className="trading-side-panel" aria-label="Trading side panel">
          <nav aria-label="Trading panel tabs">
            <button type="button" className="active">Watchlist</button>
            <button type="button">Indicators</button>
            <button type="button">Data</button>
            <button type="button">Layout</button>
          </nav>
          <h3>Canonical instruments</h3>
          <ul>
            {(instruments.data ?? []).map((instrument) => (
              <li key={instrument.instrument_id}>
                <button type="button" onClick={() => setInstrumentId(instrument.instrument_id)}>
                  <strong>{instrument.display_symbol}</strong>
                  <small>{instrument.instrument_id}</small>
                </button>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </main>
  );
}
