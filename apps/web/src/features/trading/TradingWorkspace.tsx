import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { TradingChartGrid } from './TradingChartGrid';
import { TradingIndicatorManager } from './TradingIndicatorManager';
import { TradingWatchlist } from './TradingWatchlist';
import { tradingApi } from './tradingApi';
import type { TradingChartType } from './chart/chartAdapter';
import type { DrawingTool } from './drawings/drawingCommands';
import { useTradingWorkspacePersistence } from './persistence/useTradingWorkspacePersistence';
import { useTradingStore } from './tradingStore';
import './TradingWorkspace.css';

const drawingTools: Array<{ id: DrawingTool; label: string; glyph: string }> = [
  { id: 'cursor', label: 'Cursor', glyph: 'Cu' },
  { id: 'trend-line', label: 'Trend line', glyph: 'Tr' },
  { id: 'horizontal-line', label: 'Horizontal line', glyph: 'Hz' },
];

export function TradingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [focusMode, setFocusMode] = useState(false);
  const persistenceStatus = useTradingWorkspacePersistence();
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });
  const layout = useTradingStore((state) => state.layout);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const links = useTradingStore((state) => state.links);
  const setLayout = useTradingStore((state) => state.setLayout);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const setDrawingTool = useTradingStore((state) => state.setDrawingTool);
  const updateChart = useTradingStore((state) => state.updateChart);
  const toggleIndicator = useTradingStore((state) => state.toggleIndicator);
  const setLink = useTradingStore((state) => state.setLink);
  const activeChart = charts.find((chart) => chart.chartId === activeChartId) ?? charts[0];
  const availableBindings = useMemo(
    () => (providers.data ?? []).flatMap((provider) => provider.bindings)
      .filter((binding) => binding.instrument_id === activeChart.instrumentId),
    [activeChart.instrumentId, providers.data],
  );
  const selectedBinding = availableBindings.find((binding) => binding.binding_id === activeChart.bindingId)
    ?? availableBindings[0];

  return (
    <main className={`trading-workspace${focusMode ? ' trading-focus-mode' : ''}`} aria-labelledby="trading-title">
      <header className="trading-workspace-header">
        <div><p className="eyebrow">Native Omnix module</p><h2 id="trading-title">{module.label}</h2><p>{module.summary}</p></div>
        <div className="trading-header-actions"><span className={`workspace-${persistenceStatus}`}>Workspace: {persistenceStatus}</span><button type="button" onClick={() => setFocusMode((value) => !value)} aria-pressed={focusMode}>{focusMode ? 'Exit focus mode' : 'Focus mode'}</button></div>
      </header>

      <section className="trading-toolbar" aria-label="Trading toolbar">
        <label>Active chart<select aria-label="Active Trading chart" value={activeChartId} onChange={(event) => setActiveChart(event.target.value)}>{charts.map((chart) => <option key={chart.chartId} value={chart.chartId}>{chart.chartId}</option>)}</select></label>
        <label>Instrument<select aria-label="Trading instrument" value={activeChart.instrumentId} onChange={(event) => updateChart(activeChartId, { instrumentId: event.target.value })}>{(instruments.data ?? []).map((instrument) => <option key={instrument.instrument_id} value={instrument.instrument_id}>{instrument.display_symbol} · {instrument.venue}</option>)}</select></label>
        <label>Data feed<select aria-label="Trading data feed" value={selectedBinding?.binding_id ?? ''} onChange={(event) => updateChart(activeChartId, { bindingId: event.target.value || null })}>{availableBindings.map((binding) => <option key={binding.binding_id} value={binding.binding_id}>{binding.provider} · {binding.feed_type}{binding.is_official_api ? '' : ' · unofficial'}</option>)}</select></label>
        <label>Timeframe<select aria-label="Trading timeframe" value={activeChart.interval} onChange={(event) => updateChart(activeChartId, { interval: event.target.value })}>{['1m', '5m', '15m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Chart<select aria-label="Trading chart type" value={activeChart.chartType} onChange={(event) => updateChart(activeChartId, { chartType: event.target.value as TradingChartType })}><option value="candlestick">Candlestick</option><option value="line">Line</option></select></label>
        <TradingIndicatorManager indicators={activeChart.indicators} onToggle={(id) => toggleIndicator(activeChartId, id)} />
        <button type="button" onClick={() => setLayout(layout === 'one' ? 'four' : 'one')}>Layout: {layout === 'one' ? '1 chart' : '4 charts'}</button>
        <span className="trading-provider-status" data-status={selectedBinding ? 'ready' : 'unavailable'}>{selectedBinding ? `${selectedBinding.provider} · ${selectedBinding.usage_scope} · ${selectedBinding.is_official_api ? 'official' : 'unofficial'}` : 'No compatible feed'}</span>
      </section>

      <section className="trading-link-toolbar" aria-label="Chart link controls">{(Object.keys(links) as Array<keyof typeof links>).map((key) => <label key={key}><input type="checkbox" checked={links[key]} onChange={(event) => setLink(key, event.target.checked)} />Link {key === 'visibleRange' ? 'visible range' : key}</label>)}</section>

      <div className="trading-body">
        <aside className="trading-tools" aria-label="Chart drawing tools">{drawingTools.map((tool) => <button key={tool.id} type="button" className={drawingTool === tool.id ? 'active' : undefined} aria-pressed={drawingTool === tool.id} title={tool.label} aria-label={tool.label} onClick={() => setDrawingTool(tool.id)}>{tool.glyph}</button>)}</aside>
        <section className="trading-chart-shell" aria-label="Trading chart workspace"><TradingChartGrid /></section>
        <aside className="trading-side-panel" aria-label="Trading side panel"><nav aria-label="Trading panel tabs"><button type="button" className="active">Watchlist</button><button type="button">Indicators</button><button type="button">Data</button><button type="button">Layout</button></nav><TradingWatchlist instruments={instruments.data ?? []} activeInstrumentId={activeChart.instrumentId} onSelect={(instrumentId) => updateChart(activeChartId, { instrumentId })} /></aside>
      </div>
    </main>
  );
}
