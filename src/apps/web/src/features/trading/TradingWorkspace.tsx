import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { TradingChartGrid } from './TradingChartGrid';
import { TradingIndicatorManager } from './TradingIndicatorManager';
import { TradingPaperPanel } from './TradingPaperPanel';
import { TradingReplayPanel } from './TradingReplayPanel';
import { TradingResearchPanel } from './TradingResearchPanel';
import { TradingScannerPanel } from './TradingScannerPanel';
import { TradingSidePanel } from './TradingSidePanel';
import { TradingSideRail } from './TradingSideRail';
import type { TradingSideTab } from './TradingSidePanel';
import { TradingTerminalDock } from './TradingTerminalDock';
import { TradingSymbolSearch } from './TradingSymbolSearch';
import { TradingAlertToastLayer } from './TradingAlertToastLayer';
import { TradingDrawingTools } from './TradingDrawingTools';
import { tradingApi } from './tradingApi';
import type { TradingChartType } from './chart/chartAdapter';
import type { DrawingSnapMode, DrawingTool } from './drawings/drawingCommands';
import { useTradingWorkspacePersistence } from './persistence/useTradingWorkspacePersistence';
import { buildTradingWorkspaceExport, downloadTradingWorkspaceExport } from './tradingExport';
import { preferredCryptoInstrument } from './cryptoInstrumentDefaults';
import {
  aggregationBaseInterval,
  isIntervalAvailable,
  intervalCompactLabel,
  TRADING_VIEW_INTERVAL_GROUPS,
} from './tradingIntervals';
import {
  MAX_TRADING_CHARTS,
  MIN_TRADING_CHARTS,
  useTradingStore,
  type TradingLayout,
} from './tradingStore';
import type { CanonicalInstrument, ProviderBinding } from './tradingTypes';
import './TradingWorkspace.css';
import './TradingAdvanced.css';
import './TradingFlexibleLayout.css';
import './TradingCompactHeader.css';
import './TradingIndicatorMenuOverlay.css';
import './TradingToolbarAlignment.css';
import './TradingChartEnhancements.css';
import './TradingIntervalMenu.css';
import './TradingSideRail.css';
import './TradingLayoutConstraints.css';

const drawingTools: Array<{ id: DrawingTool; label: string; glyph: string }> = [
  { id: 'cursor', label: 'Cursor', glyph: '↖' },
  { id: 'alert', label: 'Place price alert', glyph: '⏰' },
  { id: 'trend-line', label: 'Trend line', glyph: '╱' },
  { id: 'horizontal-line', label: 'Horizontal line', glyph: '─' },
  { id: 'vertical-line', label: 'Vertical line', glyph: '│' },
  { id: 'ray', label: 'Ray', glyph: '↗' },
  { id: 'rectangle', label: 'Rectangle', glyph: '□' },
  { id: 'fibonacci', label: 'Fibonacci retracement', glyph: '≋' },
  { id: 'text', label: 'Text note', glyph: 'T' },
  { id: 'measurement', label: 'Measure', glyph: '↔' },
];

const gridOptions: Array<{ id: TradingLayout; label: string }> = [
  { id: 'auto', label: 'Auto grid' },
  { id: 'columns-1', label: '1 column' },
  { id: 'columns-2', label: '2 columns' },
  { id: 'columns-3', label: '3 columns' },
  { id: 'columns-4', label: '4 columns' },
];

const quickIntervalPriority = ['1h', '2h', '4h'];

const chartTypeGlyphs: Record<TradingChartType, string> = {
  candlestick: 'candles',
  bar: 'bars',
  line: 'line',
  area: 'area',
  baseline: 'baseline',
};

type ToolPanel = 'scanner' | 'replay' | 'paper' | 'research';

function preferredInterval(binding: ProviderBinding, current: string): string {
  if (isIntervalAvailable(current, binding.supported_intervals)) return current;
  for (const candidate of ['1h', '2h', '4h', '1d', '15m', '5m', '1m', '1w']) {
    if (binding.supported_intervals.includes(candidate)) return candidate;
  }
  return binding.supported_intervals[0] ?? current;
}

function intervalLabel(interval: string): string {
  return intervalCompactLabel(interval);
}

function preferredInstrument(
  instrument: CanonicalInstrument,
  instruments: readonly CanonicalInstrument[],
): CanonicalInstrument {
  return preferredCryptoInstrument(instrument, instruments);
}

export function TradingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [focusMode, setFocusMode] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [symbolSearchResults, setSymbolSearchResults] = useState<CanonicalInstrument[]>([]);
  const [symbolSearchOpen, setSymbolSearchOpen] = useState(false);
  const [symbolSearchLoading, setSymbolSearchLoading] = useState(false);
  const [toolPanel, setToolPanel] = useState<ToolPanel | null>(null);
  const [sidePanelTab, setSidePanelTab] = useState<TradingSideTab>('watchlist');
  const persistence = useTradingWorkspacePersistence();
  const workspaceHydrated = persistence.status !== 'loading';
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });
  const layout = useTradingStore((state) => state.layout);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const drawingSnapMode = useTradingStore((state) => state.drawingSnapMode);
  const links = useTradingStore((state) => state.links);
  const panels = useTradingStore((state) => state.panels);
  const favoriteInstrumentIds = useTradingStore((state) => state.favoriteInstrumentIds);
  const setLayout = useTradingStore((state) => state.setLayout);
  const setChartCount = useTradingStore((state) => state.setChartCount);
  const addChart = useTradingStore((state) => state.addChart);
  const removeChart = useTradingStore((state) => state.removeChart);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const setDrawingTool = useTradingStore((state) => state.setDrawingTool);
  const setDrawingSnapMode = useTradingStore((state) => state.setDrawingSnapMode);
  const updateChart = useTradingStore((state) => state.updateChart);
  const toggleIndicator = useTradingStore((state) => state.toggleIndicator);
  const setIndicators = useTradingStore((state) => state.setIndicators);
  const setLink = useTradingStore((state) => state.setLink);
  const setPanel = useTradingStore((state) => state.setPanel);
  const toggleFavoriteInstrument = useTradingStore((state) => state.toggleFavoriteInstrument);
  const activeChart = charts.find((chart) => chart.chartId === activeChartId) ?? charts[0];
  const availableBindings = useMemo(
    () => (providers.data ?? []).flatMap((provider) => provider.bindings ?? [])
      .filter((binding) => binding.instrument_id === activeChart.instrumentId),
    [activeChart.instrumentId, providers.data],
  );
  const selectedBinding = availableBindings.find((binding) => binding.binding_id === activeChart.bindingId)
    ?? availableBindings[0];
  const visibleInstruments = useMemo(
    () => (instruments.data ?? []).filter((instrument) => (
      instrument.asset_class !== 'crypto' || instrument.venue === 'BINANCE'
    )),
    [instruments.data],
  );
  const activeInstrument = useMemo(
    () => (instruments.data ?? []).find((instrument) => instrument.instrument_id === activeChart.instrumentId),
    [activeChart.instrumentId, instruments.data],
  );
  const supportedIntervals = selectedBinding?.supported_intervals ?? [];
  const quickIntervals = quickIntervalPriority.filter((interval) => isIntervalAvailable(interval, supportedIntervals));
  const favorite = favoriteInstrumentIds.includes(activeChart.instrumentId);

  useEffect(() => {
    if (!selectedBinding || isIntervalAvailable(activeChart.interval, selectedBinding.supported_intervals)) return;
    updateChart(activeChartId, { interval: preferredInterval(selectedBinding, activeChart.interval) });
  }, [activeChart.interval, activeChartId, selectedBinding?.binding_id, updateChart]);

  const exportWorkspace = () => downloadTradingWorkspaceExport(buildTradingWorkspaceExport({
    layout,
    activeChartId,
    charts,
    links,
  }));

  useEffect(() => {
    const query = symbolQuery.trim();
    if (!symbolSearchOpen || !query) {
      setSymbolSearchResults([]);
      setSymbolSearchLoading(false);
      return;
    }

    let cancelled = false;
    setSymbolSearchLoading(true);
    const timer = window.setTimeout(() => {
      void tradingApi.instruments(query).then((matches) => {
        if (!cancelled) {
          setSymbolSearchResults(matches);
          setSymbolSearchLoading(false);
        }
      }).catch(() => {
        if (!cancelled) {
          setSymbolSearchResults([]);
          setSymbolSearchLoading(false);
        }
      });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [symbolQuery, symbolSearchOpen]);

  const applySymbolMatch = (match: CanonicalInstrument, candidates: readonly CanonicalInstrument[]) => {
    const next = preferredInstrument(match, [...(instruments.data ?? []), ...candidates]);
    updateChart(activeChartId, { instrumentId: next.instrument_id, bindingId: null });
    setSymbolQuery(next.display_symbol);
    setSymbolSearchResults([]);
    setSymbolSearchOpen(false);
    void instruments.refetch();
    void providers.refetch();
  };

  const selectBinding = (bindingId: string) => {
    const binding = availableBindings.find((candidate) => candidate.binding_id === bindingId);
    if (!binding) return;
    updateChart(activeChartId, {
      bindingId: binding.binding_id,
      interval: preferredInterval(binding, activeChart.interval),
    });
  };

  const toggleToolPanel = (panel: ToolPanel) => {
    setToolPanel((current) => current === panel ? null : panel);
  };

  const createWorkspace = () => {
    const name = window.prompt('Workspace name', `Workspace ${persistence.workspaces.length + 1}`);
    if (name) void persistence.createWorkspace(name);
  };

  const renameWorkspace = () => {
    const name = window.prompt('Rename workspace', persistence.activeWorkspaceName);
    if (name) void persistence.renameWorkspace(name);
  };

  const deleteWorkspace = () => {
    if (persistence.workspaces.length <= 1) return;
    if (window.confirm(`Delete ${persistence.activeWorkspaceName}?`)) void persistence.deleteWorkspace();
  };

  const openSymbolSearch = () => {
    setSymbolQuery(activeInstrument?.display_symbol ?? '');
    setSymbolSearchResults([]);
    setSymbolSearchOpen(true);
  };

  const activeSymbolLabel = activeInstrument?.display_symbol
    ?? activeChart.instrumentId.split(':').at(-1)?.replace('-', '/')
    ?? 'Select symbol';

  return (
    <main className={`trading-workspace${focusMode ? ' trading-focus-mode' : ''}`} aria-labelledby="trading-title">
      <header className="trading-terminal-header">
        <div className="trading-terminal-brand">
          <span className="trading-terminal-logo" aria-hidden="true" />
          <div><strong id="trading-title">{module.label}</strong><small>Research &amp; paper terminal</small></div>
        </div>

        <div className="trading-workspace-switcher">
          <select
            aria-label="Saved Trading workspace"
            value={persistence.activeWorkspaceId}
            onChange={(event) => void persistence.selectWorkspace(event.target.value)}
            disabled={!workspaceHydrated}
          >
            {persistence.workspaces.map((workspace) => (
              <option key={workspace.workspaceId} value={workspace.workspaceId}>{workspace.name}</option>
            ))}
          </select>
          <button type="button" aria-label="Create workspace" onClick={createWorkspace} disabled={!workspaceHydrated}>+</button>
          <button type="button" aria-label="Rename workspace" onClick={renameWorkspace} disabled={!workspaceHydrated}>Rename</button>
          <button type="button" aria-label="Delete workspace" onClick={deleteWorkspace} disabled={!workspaceHydrated || persistence.workspaces.length <= 1}>Delete</button>
        </div>

        <div className="trading-layout-switcher" role="group" aria-label="Chart count and grid">
          <button type="button" onClick={() => removeChart()} disabled={charts.length <= MIN_TRADING_CHARTS} aria-label="Remove active chart">−</button>
          <select aria-label="Number of charts" value={charts.length} onChange={(event) => setChartCount(Number(event.target.value))}>
            {Array.from({ length: MAX_TRADING_CHARTS }, (_, index) => index + 1).map((count) => (
              <option key={count} value={count}>{count} chart{count === 1 ? '' : 's'}</option>
            ))}
          </select>
          <button type="button" onClick={addChart} disabled={charts.length >= MAX_TRADING_CHARTS} aria-label="Add chart">+</button>
          <select aria-label="Grid columns" value={layout} onChange={(event) => setLayout(event.target.value as TradingLayout)}>
            {gridOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </div>

        <div className="trading-header-actions">
          <span className={`workspace-${persistence.status}`}>Workspace {persistence.status}</span>
          {persistence.hasConflict ? (
            <>
              <button type="button" onClick={() => void persistence.resolveConflict('reload')}>Reload server</button>
              <button type="button" onClick={() => void persistence.resolveConflict('overwrite')}>Overwrite server</button>
            </>
          ) : null}
          <button type="button" aria-pressed={panels.right} onClick={() => setPanel('right', !panels.right)} disabled={!workspaceHydrated}>Right panel</button>
          <button type="button" aria-pressed={panels.bottom} onClick={() => setPanel('bottom', !panels.bottom)} disabled={!workspaceHydrated}>Bottom dock</button>
          <button type="button" onClick={exportWorkspace}>Export</button>
          <button type="button" onClick={() => setFocusMode((value) => !value)} aria-pressed={focusMode}>{focusMode ? 'Exit focus' : 'Focus'}</button>
      </div>
      <section className="trading-command-bar" aria-label="Trading command bar">
        <div className="trading-chart-controls" role="group" aria-label="Chart controls">
        <div className="trading-chart-symbol-options" aria-label="Chart symbol options">
        <button type="button" className="trading-symbol-trigger" aria-label="Open symbol search" onClick={openSymbolSearch}>
          <span className="trading-symbol-trigger-icon" aria-hidden="true" />
          <span className="trading-symbol-trigger-copy">
            <strong>{activeSymbolLabel}</strong>
            <small>{activeInstrument?.venue ?? 'Symbol search'}</small>
          </span>
          <span className="trading-symbol-trigger-caret" aria-hidden="true">⌄</span>
        </button>
        {/* <div className="trading-symbol-search">
          <span aria-hidden="true">⌕</span>
          <input
            list="trading-instrument-options"
            aria-label="Search Trading symbol"
            placeholder="Search symbol…"
            value={symbolQuery}
            onChange={(event) => {
              const nextQuery = event.target.value;
              setSymbolQuery(nextQuery);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') setSymbolSearchOpen(true);
            }}
          />
          <datalist id="trading-instrument-options">
            {(instruments.data ?? []).map((instrument) => <option key={instrument.instrument_id} value={instrument.display_symbol}>{instrument.venue}</option>)}
          </datalist>
        </div>
        */}
        <button
          type="button"
          className="trading-favorite"
          aria-label={favorite ? 'Remove active instrument from favorites' : 'Favorite active instrument'}
          aria-pressed={favorite}
          onClick={() => toggleFavoriteInstrument(activeChart.instrumentId)}
        >
          {favorite ? '★' : '☆'}
        </button>

        <select aria-label="Active Trading chart" value={activeChartId} onChange={(event) => setActiveChart(event.target.value)}>
          {charts.map((chart, index) => <option key={chart.chartId} value={chart.chartId}>Chart {index + 1}</option>)}
        </select>
        </div>

          <div className="trading-timeframe-buttons" role="group" aria-label="Trading timeframe">
          {quickIntervals.map((item) => (
            <button
              key={item}
              type="button"
              className={activeChart.interval === item ? 'active' : undefined}
              aria-pressed={activeChart.interval === item}
              onClick={() => updateChart(activeChartId, { interval: item })}
            >
              {intervalLabel(item)}
            </button>
          ))}
          <details className="trading-interval-manager">
            <summary
              role="combobox"
              aria-label="All supported Trading intervals"
              aria-haspopup="listbox"
            >
              <span>{intervalLabel(activeChart.interval)}</span>
              <span className="trading-menu-caret" aria-hidden="true">⌄</span>
            </summary>
            <div className="trading-interval-menu" role="listbox" aria-label="TradingView intervals">
              {TRADING_VIEW_INTERVAL_GROUPS.map((group) => (
                <section key={group.label} className="trading-interval-group" role="group" aria-label={group.label}>
                  <header>{group.label}<span aria-hidden="true">⌃</span></header>
                  {group.options.map((option) => {
                    const baseInterval = aggregationBaseInterval(option.value, supportedIntervals);
                    const supported = baseInterval !== null;
                    const derived = baseInterval !== null && baseInterval !== option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        role="option"
                        aria-selected={activeChart.interval === option.value}
                        disabled={!supported}
                        title={supported
                          ? derived
                            ? `${option.label} · calculated from ${intervalLabel(baseInterval)}`
                            : option.label
                          : `${option.label} is not supported by ${selectedBinding?.provider ?? 'the selected feed'}`}
                        onClick={(event) => {
                          updateChart(activeChartId, { interval: option.value });
                          event.currentTarget.closest('details')?.removeAttribute('open');
                        }}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </section>
              ))}
            </div>
          </details>
          </div>

          <label className="trading-chart-type-control" title={`Chart type: ${activeChart.chartType}`}>
            <span className={`trading-chart-type-glyph ${chartTypeGlyphs[activeChart.chartType]}`} aria-hidden="true"><i /><i /><i /></span>
            <select aria-label="Trading chart type" value={activeChart.chartType} onChange={(event) => updateChart(activeChartId, { chartType: event.target.value as TradingChartType })}>
              {(['candlestick', 'bar', 'line', 'area', 'baseline'] as TradingChartType[]).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <TradingIndicatorManager indicators={activeChart.indicators} onToggle={(id) => toggleIndicator(activeChartId, id)} />
        </div>

        <select aria-label="Trading data feed" value={selectedBinding?.binding_id ?? ''} onChange={(event) => selectBinding(event.target.value)}>
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
      </header>

      <TradingSymbolSearch
        open={symbolSearchOpen}
        query={symbolQuery}
        instruments={[...(instruments.data ?? []), ...symbolSearchResults]}
        activeInstrumentId={activeChart.instrumentId}
        loading={symbolSearchLoading}
        onQueryChange={setSymbolQuery}
        onSelect={(match) => applySymbolMatch(match, [match])}
        onClose={() => setSymbolSearchOpen(false)}
      />
      <TradingAlertToastLayer />

      <div className="trading-body">
        <TradingDrawingTools selectedTool={drawingTool} onSelect={setDrawingTool} />
        <section className="trading-chart-shell" aria-label="Trading chart workspace"><TradingChartGrid /></section>
        {workspaceHydrated ? (
          <div className={`trading-right-dock ${panels.right ? 'is-expanded' : 'is-collapsed'}`}>
            {panels.right ? (
              <TradingSidePanel
                instruments={visibleInstruments}
                activeInstrumentId={activeChart.instrumentId}
                bindingId={selectedBinding?.binding_id ?? activeChart.bindingId}
                interval={activeChart.interval}
                selectedTab={sidePanelTab}
                onTabChange={setSidePanelTab}
                indicators={activeChart.indicators}
                layout={layout}
                chartCount={charts.length}
                minimumChartCount={MIN_TRADING_CHARTS}
                maximumChartCount={MAX_TRADING_CHARTS}
                links={links}
                snapMode={drawingSnapMode}
                onSelectInstrument={(instrumentId) => {
                  const instrument = (instruments.data ?? []).find((item) => item.instrument_id === instrumentId);
                  const next = instrument ? preferredInstrument(instrument, instruments.data ?? []) : null;
                  updateChart(activeChartId, { instrumentId: next?.instrument_id ?? instrumentId, bindingId: null });
                }}
                onSetIndicators={(next) => setIndicators(activeChartId, next)}
                onSetLayout={setLayout}
                onSetChartCount={setChartCount}
                onAddChart={addChart}
                onRemoveChart={() => removeChart()}
                onSetLink={setLink}
                onSetSnapMode={(mode: DrawingSnapMode) => setDrawingSnapMode(mode)}
                onOpenResearch={() => setToolPanel('research')}
              />
            ) : null}
            <TradingSideRail
              activeTab={sidePanelTab}
              collapsed={!panels.right}
              onSelectTab={setSidePanelTab}
              onToggle={() => setPanel('right', !panels.right)}
            />
          </div>
        ) : null}
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

      {workspaceHydrated && panels.bottom ? <TradingTerminalDock instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} /> : null}

    </main>
  );
}
