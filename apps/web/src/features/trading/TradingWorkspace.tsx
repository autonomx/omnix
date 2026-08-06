import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { TradingChartGrid } from './TradingChartGrid';
import { TradingComplianceFooter } from './TradingComplianceFooter';
import { TradingIndicatorManager } from './TradingIndicatorManager';
import { TradingPaperPanel } from './TradingPaperPanel';
import { TradingReplayPanel } from './TradingReplayPanel';
import { TradingResearchPanel } from './TradingResearchPanel';
import { TradingScannerPanel } from './TradingScannerPanel';
import { TradingSidePanel } from './TradingSidePanel';
import { TradingTerminalDock } from './TradingTerminalDock';
import { tradingApi } from './tradingApi';
import type { TradingChartType } from './chart/chartAdapter';
import type { DrawingSnapMode, DrawingTool } from './drawings/drawingCommands';
import { useTradingWorkspacePersistence } from './persistence/useTradingWorkspacePersistence';
import { buildTradingWorkspaceExport, downloadTradingWorkspaceExport } from './tradingExport';
import { useTradingStore, type TradingLayout } from './tradingStore';
import './TradingWorkspace.css';
import './TradingAdvanced.css';

const drawingTools: Array<{ id: DrawingTool; label: string; glyph: string }> = [
  { id: 'cursor', label: 'Cursor', glyph: '↖' },
  { id: 'trend-line', label: 'Trend line', glyph: '╱' },
  { id: 'horizontal-line', label: 'Horizontal line', glyph: '─' },
  { id: 'vertical-line', label: 'Vertical line', glyph: '│' },
  { id: 'ray', label: 'Ray', glyph: '↗' },
  { id: 'rectangle', label: 'Rectangle', glyph: '□' },
  { id: 'fibonacci', label: 'Fibonacci retracement', glyph: '≋' },
  { id: 'text', label: 'Text note', glyph: 'T' },
  { id: 'measurement', label: 'Measure', glyph: '↔' },
];

const layoutOptions: Array<{ id: TradingLayout; label: string; glyph: string }> = [
  { id: 'one', label: 'Single chart', glyph: '□' },
  { id: 'two-horizontal', label: 'Two columns', glyph: '▥' },
  { id: 'two-vertical', label: 'Two rows', glyph: '▤' },
  { id: 'four', label: 'Four charts', glyph: '▦' },
];

type ToolPanel = 'scanner' | 'replay' | 'paper' | 'research';

export function TradingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [focusMode, setFocusMode] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [toolPanel, setToolPanel] = useState<ToolPanel | null>(null);
  const persistenceStatus = useTradingWorkspacePersistence();
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });
  const layout = useTradingStore((state) => state.layout);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const drawingSnapMode = useTradingStore((state) => state.drawingSnapMode);
  const links = useTradingStore((state) => state.links);
  const setLayout = useTradingStore((state) => state.setLayout);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const setDrawingTool = useTradingStore((state) => state.setDrawingTool);
  const setDrawingSnapMode = useTradingStore((state) => state.setDrawingSnapMode);
  const updateChart = useTradingStore((state) => state.updateChart);
  const toggleIndicator = useTradingStore((state) => state.toggleIndicator);
  const setIndicators = useTradingStore((state) => state.setIndicators);
  const setLink = useTradingStore((state) => state.setLink);
  const activeChart = charts.find((chart) => chart.chartId === activeChartId) ?? charts[0];
  const availableBindings = useMemo(
    () => (providers.data ?? []).flatMap((provider) => provider.bindings)
      .filter((binding) => binding.instrument_id === activeChart.instrumentId),
    [activeChart.instrumentId, providers.data],
  );
  const selectedBinding = availableBindings.find((binding) => binding.binding_id === activeChart.bindingId)
    ?? availableBindings[0];
  const selectedProvider = (providers.data ?? []).find(
    (provider) => provider.provider === selectedBinding?.provider,
  ) ?? null;

  const exportWorkspace = () => downloadTradingWorkspaceExport(buildTradingWorkspaceExport({
    layout,
    activeChartId,
    charts,
    links,
  }));

  const selectSymbol = () => {
    const query = symbolQuery.trim().toUpperCase();
    if (!query) return;
    const match = (instruments.data ?? []).find((instrument) => (
      instrument.display_symbol.toUpperCase() === query
      || instrument.venue_symbol.toUpperCase() === query
      || instrument.display_symbol.toUpperCase().startsWith(query)
      || instrument.venue_symbol.toUpperCase().startsWith(query)
    ));
    if (!match) return;
    updateChart(activeChartId, { instrumentId: match.instrument_id, bindingId: null });
    setSymbolQuery(match.display_symbol);
  };

  const toggleToolPanel = (panel: ToolPanel) => {
    setToolPanel((current) => current === panel ? null : panel);
  };

  return (
    <main className={`trading-workspace${focusMode ? ' trading-focus-mode' : ''}`} aria-labelledby="trading-title">
      <header className="trading-terminal-header">
        <div className="trading-terminal-brand">
          <span className="trading-terminal-logo" aria-hidden="true" />
          <div><strong id="trading-title">{module.label}</strong><small>Research &amp; paper terminal</small></div>
        </div>

        <div className="trading-workspace-switcher">
          <button type="button">Main Workspace <span aria-hidden="true">⌄</span></button>
          <button type="button" aria-label="Create workspace">+</button>
        </div>

        <div className="trading-layout-switcher" role="group" aria-label="Chart layout">
          {layoutOptions.map((item) => (
            <button
              key={item.id}
              type="button"
              className={layout === item.id ? 'active' : undefined}
              aria-pressed={layout === item.id}
              aria-label={item.label}
              title={item.label}
              onClick={() => setLayout(item.id)}
            >
              {item.glyph}
            </button>
          ))}
          <span>{layout === 'four' ? '4 Charts' : layout === 'one' ? '1 Chart' : '2 Charts'}</span>
        </div>

        <div className="trading-header-actions">
          <span className={`workspace-${persistenceStatus}`}>Workspace {persistenceStatus}</span>
          <button type="button" onClick={exportWorkspace}>Export</button>
          <button type="button" onClick={() => setFocusMode((value) => !value)} aria-pressed={focusMode}>{focusMode ? 'Exit focus' : 'Focus'}</button>
        </div>
      </header>

      <section className="trading-command-bar" aria-label="Trading command bar">
        <div className="trading-symbol-search">
          <span aria-hidden="true">⌕</span>
          <input
            list="trading-instrument-options"
            aria-label="Search Trading symbol"
            placeholder="Search symbol…"
            value={symbolQuery}
            onChange={(event) => setSymbolQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') selectSymbol();
            }}
          />
          <datalist id="trading-instrument-options">
            {(instruments.data ?? []).map((instrument) => <option key={instrument.instrument_id} value={instrument.display_symbol}>{instrument.venue}</option>)}
          </datalist>
        </div>
        <button type="button" className="trading-favorite" aria-label="Favorite active instrument">☆</button>

        <select aria-label="Active Trading chart" value={activeChartId} onChange={(event) => setActiveChart(event.target.value)}>
          {charts.map((chart) => <option key={chart.chartId} value={chart.chartId}>{chart.chartId.replace('-', ' ')}</option>)}
        </select>

        <div className="trading-timeframe-buttons" role="group" aria-label="Trading timeframe">
          {['1m', '5m', '15m', '1h', '4h', '1d', '1w'].map((item) => (
            <button
              key={item}
              type="button"
              className={activeChart.interval === item ? 'active' : undefined}
              aria-pressed={activeChart.interval === item}
              onClick={() => updateChart(activeChartId, { interval: item })}
            >
              {item.toUpperCase()}
            </button>
          ))}
        </div>

        <select aria-label="Trading chart type" value={activeChart.chartType} onChange={(event) => updateChart(activeChartId, { chartType: event.target.value as TradingChartType })}>
          {(['candlestick', 'bar', 'line', 'area', 'baseline'] as TradingChartType[]).map((item) => <option key={item} value={item}>{item}</option>)}
        </select>

        <TradingIndicatorManager indicators={activeChart.indicators} onToggle={(id) => toggleIndicator(activeChartId, id)} />

        <select aria-label="Trading data feed" value={selectedBinding?.binding_id ?? ''} onChange={(event) => updateChart(activeChartId, { bindingId: event.target.value || null })}>
          {availableBindings.map((binding) => <option key={binding.binding_id} value={binding.binding_id}>{binding.provider}{binding.is_official_api ? '' : ' · unofficial'}</option>)}
        </select>

        <div className="trading-tool-shortcuts" role="group" aria-label="Trading tools">
          <button type="button" aria-pressed={toolPanel === 'scanner'} onClick={() => toggleToolPanel('scanner')}>Scanner</button>
          <button type="button" aria-pressed={toolPanel === 'replay'} onClick={() => toggleToolPanel('replay')}>Backtest</button>
          <button type="button" aria-pressed={toolPanel === 'paper'} onClick={() => toggleToolPanel('paper')}>Paper</button>
          <button type="button" aria-pressed={toolPanel === 'research'} onClick={() => toggleToolPanel('research')}>AI Research</button>
        </div>

        <span className="trading-provider-status" data-status={selectedBinding ? 'ready' : 'unavailable'} title={selectedBinding ? `${selectedBinding.provider} · ${selectedBinding.usage_scope} · ${selectedBinding.is_official_api ? 'official' : 'unofficial'}` : 'No compatible feed'}>
          <i aria-hidden="true" />{selectedBinding ? selectedBinding.provider : 'No feed'}
        </span>
      </section>

      <div className="trading-body">
        <aside className="trading-tools" aria-label="Chart drawing tools">
          {drawingTools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              className={drawingTool === tool.id ? 'active' : undefined}
              aria-pressed={drawingTool === tool.id}
              title={tool.label}
              aria-label={tool.label}
              onClick={() => setDrawingTool(tool.id)}
            >
              {tool.glyph}
            </button>
          ))}
        </aside>
        <section className="trading-chart-shell" aria-label="Trading chart workspace"><TradingChartGrid /></section>
        <TradingSidePanel
          instruments={instruments.data ?? []}
          activeInstrumentId={activeChart.instrumentId}
          indicators={activeChart.indicators}
          layout={layout}
          links={links}
          snapMode={drawingSnapMode}
          onSelectInstrument={(instrumentId) => updateChart(activeChartId, { instrumentId, bindingId: null })}
          onSetIndicators={(next) => setIndicators(activeChartId, next)}
          onSetLayout={setLayout}
          onSetLink={setLink}
          onSetSnapMode={(mode: DrawingSnapMode) => setDrawingSnapMode(mode)}
          onOpenResearch={() => setToolPanel('research')}
        />
      </div>

      {toolPanel ? (
        <section className="trading-tool-drawer" aria-label="Trading analysis tool">
          <header>
            <strong>{toolPanel === 'scanner' ? 'Market scanner' : toolPanel === 'replay' ? 'Replay & backtest' : toolPanel === 'paper' ? 'Paper account manager' : 'AI market research'}</strong>
            <button type="button" onClick={() => setToolPanel(null)} aria-label="Close analysis tool">×</button>
          </header>
          <div>
            {toolPanel === 'scanner' ? <TradingScannerPanel instruments={instruments.data ?? []} /> : null}
            {toolPanel === 'replay' ? (
              <TradingReplayPanel instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} interval={activeChart.interval} />
            ) : null}
            {toolPanel === 'paper' ? <TradingPaperPanel instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} /> : null}
            {toolPanel === 'research' ? (
              <TradingResearchPanel instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} interval={activeChart.interval} />
            ) : null}
          </div>
        </section>
      ) : null}

      <TradingTerminalDock instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} />

      <TradingComplianceFooter provider={selectedProvider} binding={selectedBinding ?? null} />
    </main>
  );
}
