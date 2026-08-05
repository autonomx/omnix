import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { tradingApi } from './tradingApi';
import './TradingWorkspace.css';

export function TradingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [focusMode, setFocusMode] = useState(false);
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });

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
          <select aria-label="Trading instrument" defaultValue={instruments.data?.[0]?.instrument_id ?? ''}>
            {(instruments.data ?? []).map((instrument) => (
              <option key={instrument.instrument_id} value={instrument.instrument_id}>
                {instrument.display_symbol} · {instrument.venue}
              </option>
            ))}
          </select>
        </label>
        <label>
          Timeframe
          <select aria-label="Trading timeframe" defaultValue="1m">
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((interval) => <option key={interval}>{interval}</option>)}
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
          <div className="trading-chart-empty">
            <strong>Charting foundation ready</strong>
            <span>Historical and live series arrive in OTT-2 and OTT-3.</span>
          </div>
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
                <strong>{instrument.display_symbol}</strong>
                <small>{instrument.instrument_id}</small>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </main>
  );
}
