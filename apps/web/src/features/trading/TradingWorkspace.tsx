import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { TradingChartGrid } from './TradingChartGrid';
import { tradingApi } from './tradingApi';
import type { TradingChartType } from './chart/chartAdapter';
import { useTradingStore } from './tradingStore';
import './TradingWorkspace.css';

export function TradingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [focusMode, setFocusMode] = useState(false);
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });
  const layout = useTradingStore((state) => state.layout);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const links = useTradingStore((state) => state.links);
  const setLayout = useTradingStore((state) => state.setLayout);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const updateChart = useTradingStore((state) => state.updateChart);
  const setLink = useTradingStore((state) => state.setLink);
  const activeChart = charts.find((chart) => chart.chartId === activeChartId) ?? charts[0];

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
          Active chart
          <select aria-label="Active Trading chart" value={activeChartId} onChange={(event) => setActiveChart(event.target.value)}>
            {charts.map((chart) => <option key={chart.chartId} value={chart.chartId}>{chart.chartId}</option>)}
          </select>
        </label>
        <label>
          Instrument
          <select
            aria-label="Trading instrument"
            value={activeChart.instrumentId}
            onChange={(event) => updateChart(activeChartId, { instrumentId: event.target.value })}
          >
            {(instruments.data ?? []).map((instrument) => (
              <option key={instrument.instrument_id} value={instrument.instrument_id}>
                {instrument.display_symbol} · {instrument.venue}
              </option>
            ))}
          </select>
        </label>
        <label>
          Timeframe
          <select
            aria-label="Trading timeframe"
            value={activeChart.interval}
            onChange={(event) => updateChart(activeChartId, { interval: event.target.value })}
          >
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Chart
          <select
            aria-label="Trading chart type"
            value={activeChart.chartType}
            onChange={(event) => updateChart(activeChartId, { chartType: event.target.value as TradingChartType })}
          >
            <option value="candlestick">Candlestick</option>
            <option value="line">Line</option>
          </select>
        </label>
        <button type="button">Indicators</button>
        <button type="button" onClick={() => setLayout(layout === 'one' ? 'four' : 'one')}>
          Layout: {layout === 'one' ? '1 chart' : '4 charts'}
        </button>
        <span className="trading-provider-status" data-status={providers.data?.[0]?.status ?? 'unavailable'}>
          {providers.isLoading ? 'Loading data provider…' : `${providers.data?.[0]?.display_name ?? 'Provider unavailable'} · ${providers.data?.[0]?.status ?? 'unavailable'}`}
        </span>
      </section>

      <section className="trading-link-toolbar" aria-label="Chart link controls">
        {(Object.keys(links) as Array<keyof typeof links>).map((key) => (
          <label key={key}>
            <input type="checkbox" checked={links[key]} onChange={(event) => setLink(key, event.target.checked)} />
            Link {key === 'visibleRange' ? 'visible range' : key}
          </label>
        ))}
      </section>

      <div className="trading-body">
        <aside className="trading-tools" aria-label="Chart drawing tools">
          {['Cursor', 'Crosshair', 'Trend line', 'Horizontal line', 'Measure'].map((tool) => (
            <button key={tool} type="button" title={tool} aria-label={tool}>{tool.slice(0, 2)}</button>
          ))}
        </aside>
        <section className="trading-chart-shell" aria-label="Trading chart workspace">
          <TradingChartGrid />
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
                <button type="button" onClick={() => updateChart(activeChartId, { instrumentId: instrument.instrument_id })}>
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
