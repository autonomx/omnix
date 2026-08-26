import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useEffect, useMemo, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { TradingChartGrid } from './TradingChartGrid';
import { TradingIndicatorManager } from './TradingIndicatorManager';
import { TradingReplayPanel } from './TradingReplayPanel';
import { TradingResearchPanel } from './TradingResearchPanel';
import { TradingScannerPanel } from './TradingScannerPanel';
import { TradingStrategiesPanel } from './TradingStrategiesPanel';
import { TradingSidePanel } from './TradingSidePanel';
import { TradingSideRail } from './TradingSideRail';
import type { TradingSideTab } from './TradingSidePanel';
import type { CoreIndicatorId } from './indicators/coreIndicators';
import { TradingTerminalDock } from './TradingTerminalDock';
import { TradingSymbolSearch, type TradingFormulaSearchPreview } from './TradingSymbolSearch';
import { TradingAlertToastLayer } from './TradingAlertToastLayer';
import { TradingDrawingTools } from './TradingDrawingTools';
import { TradingSessionTabs } from './TradingSessionTabs';
import { tradingApi } from './tradingApi';
import type { DrawingSnapMode } from './drawings/drawingCommands';
import { TradingChartTypeMenu } from './TradingChartTypeMenu';
import { TradingChartLayoutPicker } from './TradingChartLayoutPicker';
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
  MAX_TRADING_TABS,
  MIN_TRADING_CHARTS,
  useTradingStore,
  type TradingLayout,
} from './tradingStore';
import type { CanonicalInstrument, ProviderBinding, TradingAlert } from './tradingTypes';
import { encodeTradingFormula, parseTradingFormula, tradingFormulaDisplaySymbol } from './tradingFormula';
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
import './TradingLightTheme.css';
import './TradingChartPan.css';
import './TradingChartChrome.css';
import './TradingTypography.css';
import './TradingToolFullscreen.css';
import './TradingSessionTabs.css';
import './TradingChartLayoutPicker.css';

const gridOptions: Array<{ id: TradingLayout; label: string }> = [
  { id: 'auto', label: 'Auto grid' },
  { id: 'columns-1', label: '1 column' },
  { id: 'columns-2', label: '2 columns' },
  { id: 'columns-3', label: '3 columns' },
  { id: 'columns-4', label: '4 columns' },
];

const quickIntervalPriority = ['1h', '2h', '4h'];

type ToolPanel = 'scanner' | 'replay' | 'strategies' | 'research';
type FormulaResolution = TradingFormulaSearchPreview & { operands: Record<string, string> };

// TradingSidePanel mounts TradingPaperPanel in the dedicated Trade tab.

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
  const navigate = useNavigate();
  const [focusMode, setFocusMode] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [symbolSearchResults, setSymbolSearchResults] = useState<CanonicalInstrument[]>([]);
  const [symbolSearchOpen, setSymbolSearchOpen] = useState(false);
  const [symbolSearchChartId, setSymbolSearchChartId] = useState<string | null>(null);
  const [symbolSearchLoading, setSymbolSearchLoading] = useState(false);
  const [formulaResolution, setFormulaResolution] = useState<FormulaResolution | null>(null);
  const [toolPanel, setToolPanel] = useState<ToolPanel | null>(null);
  const [toolPanelFullscreen, setToolPanelFullscreen] = useState(false);
  const [sidePanelTab, setSidePanelTab] = useState<TradingSideTab>('watchlist');
  const [pineIndicatorId, setPineIndicatorId] = useState<CoreIndicatorId | null>(null);
  const [paperAccountId, setPaperAccountId] = useState<string | null>(null);
  const persistence = useTradingWorkspacePersistence();
  const workspaceHydrated = persistence.status !== 'loading';
  const providers = useQuery({ queryKey: ['trading', 'providers'], queryFn: tradingApi.providers });
  const instruments = useQuery({ queryKey: ['trading', 'instruments'], queryFn: () => tradingApi.instruments() });
  const layout = useTradingStore((state) => state.layout);
  const tabs = useTradingStore((state) => state.tabs);
  const activeTabId = useTradingStore((state) => state.activeTabId);
  const charts = useTradingStore((state) => state.charts);
  const activeChartId = useTradingStore((state) => state.activeChartId);
  const replayMode = useTradingStore((state) => state.replayMode);
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const drawingSnapMode = useTradingStore((state) => state.drawingSnapMode);
  const links = useTradingStore((state) => state.links);
  const panels = useTradingStore((state) => state.panels);
  const favoriteInstrumentIds = useTradingStore((state) => state.favoriteInstrumentIds);
  const setLayout = useTradingStore((state) => state.setLayout);
  const setActiveTab = useTradingStore((state) => state.setActiveTab);
  const addTab = useTradingStore((state) => state.addTab);
  const removeTab = useTradingStore((state) => state.removeTab);
  const setChartCount = useTradingStore((state) => state.setChartCount);
  const addChart = useTradingStore((state) => state.addChart);
  const removeChart = useTradingStore((state) => state.removeChart);
  const setActiveChart = useTradingStore((state) => state.setActiveChart);
  const setReplayMode = useTradingStore((state) => state.setReplayMode);
  const setDrawingTool = useTradingStore((state) => state.setDrawingTool);
  const setDrawingSnapMode = useTradingStore((state) => state.setDrawingSnapMode);
  const updateChart = useTradingStore((state) => state.updateChart);
  const toggleIndicator = useTradingStore((state) => state.toggleIndicator);
  const updateIndicator = useTradingStore((state) => state.updateIndicator);
  const setIndicators = useTradingStore((state) => state.setIndicators);
  const setLink = useTradingStore((state) => state.setLink);
  const setPanel = useTradingStore((state) => state.setPanel);
  const toggleFavoriteInstrument = useTradingStore((state) => state.toggleFavoriteInstrument);
  const activeChart = charts.find((chart) => chart.chartId === activeChartId) ?? charts[0];
  const providerBindings = useMemo(
    () => {
      const bindingsById = new Map<string, ProviderBinding>();
      for (const binding of (providers.data ?? []).flatMap((provider) => provider.bindings ?? [])) {
        if (!bindingsById.has(binding.binding_id)) bindingsById.set(binding.binding_id, binding);
      }
      return [...bindingsById.values()];
    },
    [providers.data],
  );
  const availableBindings = useMemo(
    () => providerBindings.filter((binding) => binding.instrument_id === activeChart.instrumentId),
    [activeChart.instrumentId, providerBindings],
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
    if (!activeInstrument) return;
    const preferred = preferredInstrument(activeInstrument, instruments.data ?? []);
    if (preferred.instrument_id === activeChart.instrumentId) return;
    updateChart(activeChartId, { instrumentId: preferred.instrument_id, bindingId: null });
  }, [activeChart.instrumentId, activeChartId, activeInstrument, instruments.data, updateChart]);

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
      setFormulaResolution(null);
      return;
    }

    const formulaHints = (instruments.data ?? []).flatMap((instrument) => [
      instrument.display_symbol,
      instrument.venue_symbol,
      instrument.instrument_id,
    ]);
    const formula = parseTradingFormula(query, { symbolHints: formulaHints });
    let cancelled = false;
    setSymbolSearchLoading(true);
    if (formula) {
      setFormulaResolution({ formula, operands: {}, unresolvedSymbols: formula.symbols, loading: true });
      const resolve = async () => {
        const matches = await Promise.all(formula.symbols.map((symbol) => tradingApi.instruments(symbol)));
        if (cancelled) return;
        const candidates = matches.flat();
        const operands: Record<string, string> = {};
        const unresolvedSymbols: string[] = [];
        for (const symbol of formula.symbols) {
          const normalized = symbol.toUpperCase();
          const symbolCandidates = [...(instruments.data ?? []), ...candidates]
            .filter((instrument, index, all) => all.findIndex((item) => item.instrument_id === instrument.instrument_id) === index)
            .filter((instrument) => [instrument.display_symbol, instrument.venue_symbol, instrument.instrument_id]
              .some((value) => value.toUpperCase() === normalized || value.toUpperCase().replace(/[-:_/]/g, '') === normalized.replace(/[-:_/]/g, '')))
            .sort((left, right) => left.display_symbol.localeCompare(right.display_symbol) || left.venue.localeCompare(right.venue));
          const match = symbolCandidates[0];
          if (!match) unresolvedSymbols.push(symbol);
          else operands[symbol] = preferredInstrument(match, symbolCandidates).instrument_id;
        }
        setSymbolSearchResults(candidates);
        setFormulaResolution({ formula, operands, unresolvedSymbols, loading: false });
        setSymbolSearchLoading(false);
      };
      void resolve().catch(() => {
        if (!cancelled) {
          setFormulaResolution({ formula, operands: {}, unresolvedSymbols: formula.symbols, loading: false });
          setSymbolSearchResults([]);
          setSymbolSearchLoading(false);
        }
      });
      return () => {
        cancelled = true;
      };
    }
    setFormulaResolution(null);
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
  }, [instruments.data, symbolQuery, symbolSearchOpen]);

  const applySymbolMatch = (match: CanonicalInstrument, candidates: readonly CanonicalInstrument[]) => {
    const next = preferredInstrument(match, [...(instruments.data ?? []), ...candidates]);
    const targetChartId = symbolSearchChartId ?? activeChartId;
    updateChart(targetChartId, { instrumentId: next.instrument_id, bindingId: null });
    setActiveChart(targetChartId);
    setSymbolQuery(next.display_symbol);
    setSymbolSearchResults([]);
    setSymbolSearchOpen(false);
    setSymbolSearchChartId(null);
    void instruments.refetch();
    void providers.refetch();
  };

  const applyFormulaResolution = (resolution: FormulaResolution | null) => {
    if (!resolution || resolution.loading) return;
    const targetChartId = symbolSearchChartId ?? activeChartId;
    const operands = Object.fromEntries(
      resolution.formula.symbols.map((symbol) => [symbol, resolution.operands[symbol] ?? symbol]),
    );
    const instrumentId = encodeTradingFormula(resolution.formula.expression, operands);
    updateChart(targetChartId, { instrumentId, bindingId: null });
    setActiveChart(targetChartId);
    setSymbolQuery(resolution.formula.expression);
    setSymbolSearchResults([]);
    setFormulaResolution(null);
    setSymbolSearchOpen(false);
    setSymbolSearchChartId(null);
  };

  const selectBinding = (bindingId: string) => {
    const binding = availableBindings.find((candidate) => candidate.binding_id === bindingId);
    if (!binding) return;
    updateChart(activeChartId, {
      bindingId: binding.binding_id,
      interval: preferredInterval(binding, activeChart.interval),
    });
  };

  const navigateToAlert = (alert: TradingAlert) => {
    const alertInterval = alert.evaluation_policy.interval;
    const activateAlertIndicator = (chartId: string) => {
      const indicatorId = alert.parameters.indicator_id;
      if (!indicatorId) return;

      const indicator = charts
        .find((chart) => chart.chartId === chartId)
        ?.indicators.find((candidate) => candidate.id === indicatorId);
      const period = alert.parameters.period;

      if (!indicator) {
        toggleIndicator(chartId, indicatorId, period);
        return;
      }
      if (!indicator.enabled) {
        toggleIndicator(chartId, indicatorId, period);
        return;
      }
      if (indicator.period !== period) updateIndicator(chartId, indicatorId, { period });
    };
    const matchingChart = charts.find((chart) => (
      chart.instrumentId === alert.instrument_id
      && Boolean(alert.binding_id)
      && chart.bindingId === alert.binding_id
    )) ?? charts.find((chart) => chart.instrumentId === alert.instrument_id);

    if (matchingChart) {
      updateChart(matchingChart.chartId, {
        interval: alertInterval,
        ...(alert.binding_id ? { bindingId: alert.binding_id } : {}),
      });
      setActiveChart(matchingChart.chartId);
      activateAlertIndicator(matchingChart.chartId);
      return;
    }

    const instrument = (instruments.data ?? []).find((item) => item.instrument_id === alert.instrument_id);
    const preferred = instrument ? preferredInstrument(instrument, instruments.data ?? []) : null;
    updateChart(activeChartId, {
      instrumentId: preferred?.instrument_id ?? alert.instrument_id,
      bindingId: alert.binding_id ?? null,
      interval: alertInterval,
    });
    setActiveChart(activeChartId);
    activateAlertIndicator(activeChartId);
  };

  const toggleToolPanel = (panel: ToolPanel) => {
    setToolPanelFullscreen(false);
    setToolPanel((current) => current === panel ? null : panel);
  };

  const openPaperTrading = () => {
    setSidePanelTab('paper');
    setPanel('right', true);
    setToolPanelFullscreen(false);
    setToolPanel(null);
  };

  useEffect(() => {
    if (!toolPanelFullscreen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setToolPanelFullscreen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toolPanelFullscreen]);

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

  const createTab = () => {
    addTab();
  };

  const sessionTabLabel = (tab: (typeof tabs)[number]) => {
    const chart = tab.charts.find((item) => item.chartId === tab.activeChartId) ?? tab.charts[0];
    if (!chart) return tab.name;
    const instrument = (instruments.data ?? []).find((item) => item.instrument_id === chart.instrumentId);
    return instrument?.display_symbol
      ?? tradingFormulaDisplaySymbol(chart.instrumentId)
      ?? chart.instrumentId.split(':').at(-1)?.replace('-', '/')
      ?? tab.name;
  };

  const closeTabSession = (tab: (typeof tabs)[number]) => {
    if (tabs.length <= 1) return;
    if (window.confirm(`Close ${sessionTabLabel(tab)}?`)) removeTab(tab.tabId);
  };

  const openSymbolSearch = (chartId = activeChartId) => {
    const targetChart = charts.find((chart) => chart.chartId === chartId) ?? activeChart;
    const targetInstrument = (instruments.data ?? []).find((instrument) => instrument.instrument_id === targetChart.instrumentId);
    setActiveChart(targetChart.chartId);
    setSymbolSearchChartId(targetChart.chartId);
    setSymbolQuery(targetInstrument?.display_symbol ?? tradingFormulaDisplaySymbol(targetChart.instrumentId) ?? targetChart.instrumentId.split(':').at(-1)?.replace('-', '/') ?? '');
    setSymbolSearchResults([]);
    setFormulaResolution(null);
    setSymbolSearchOpen(true);
  };

  const openPineEditor = (id: CoreIndicatorId) => {
    setPineIndicatorId(id);
    setSidePanelTab('pine');
    setPanel('right', true);
    setToolPanelFullscreen(false);
    setToolPanel(null);
  };

  const closeSymbolSearch = () => {
    setSymbolSearchOpen(false);
    setSymbolSearchChartId(null);
    setFormulaResolution(null);
  };

  const symbolSearchTarget = charts.find((chart) => chart.chartId === symbolSearchChartId) ?? activeChart;
  const symbolSearchTargetInstrument = (instruments.data ?? []).find(
    (instrument) => instrument.instrument_id === symbolSearchTarget.instrumentId,
  );

  const activeSymbolLabel = activeInstrument?.display_symbol
    ?? tradingFormulaDisplaySymbol(activeChart.instrumentId)
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
          <TradingChartLayoutPicker
            chartCount={charts.length}
            maximumChartCount={MAX_TRADING_CHARTS}
            layout={layout}
            links={links}
            onSetChartCount={setChartCount}
            onSetLayout={setLayout}
            onSetLink={setLink}
          />
          <button type="button" onClick={addChart} disabled={charts.length >= MAX_TRADING_CHARTS} aria-label="Add chart">+</button>
          <select aria-label="Grid columns" value={gridOptions.some((option) => option.id === layout) ? layout : 'auto'} onChange={(event) => setLayout(event.target.value as TradingLayout)}>
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
        <button type="button" className="trading-symbol-trigger" aria-label="Open symbol search" onClick={() => openSymbolSearch()}>
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

          <TradingChartTypeMenu value={activeChart.chartType} onChange={(chartType) => updateChart(activeChartId, { chartType })} />

          <TradingIndicatorManager indicators={activeChart.indicators} onToggle={(id) => toggleIndicator(activeChartId, id)} />
          <button
            type="button"
            className="trading-replay-trigger trading-topbar-replay"
            aria-label={replayMode ? 'Exit replay mode' : 'Replay'}
            aria-pressed={replayMode}
            title={replayMode ? 'Exit replay mode' : 'Replay chart from a selected bar'}
            onClick={() => setReplayMode(!replayMode)}
          >
            <span className="trading-replay-trigger-icon" aria-hidden="true">◀◀</span>
            <span>Replay</span>
          </button>
        </div>

        <select aria-label="Trading data feed" value={selectedBinding?.binding_id ?? ''} onChange={(event) => selectBinding(event.target.value)}>
          {availableBindings.map((binding) => <option key={binding.binding_id} value={binding.binding_id}>{binding.provider}{binding.is_official_api ? '' : ' · unofficial'}</option>)}
        </select>

        <div className="trading-tool-shortcuts" role="group" aria-label="Trading tools">
          <button type="button" aria-pressed={toolPanel === 'scanner'} onClick={() => toggleToolPanel('scanner')}>Scanner</button>
          <button type="button" aria-pressed={toolPanel === 'replay'} onClick={() => toggleToolPanel('replay')}>Backtest</button>
          <button type="button" aria-pressed={toolPanel === 'strategies'} onClick={() => toggleToolPanel('strategies')}>Strategies</button>
          <button type="button" aria-pressed={sidePanelTab === 'paper' && panels.right} onClick={openPaperTrading}>Trade</button>
          <button type="button" aria-pressed={toolPanel === 'research'} onClick={() => toggleToolPanel('research')}>AI Research</button>
        </div>

        <span className="trading-provider-status" data-status={selectedBinding ? 'ready' : 'unavailable'} title={selectedBinding ? `${selectedBinding.provider} · ${selectedBinding.usage_scope} · ${selectedBinding.is_official_api ? 'official' : 'unofficial'}` : 'No compatible feed'}>
          <i aria-hidden="true" />{selectedBinding ? selectedBinding.provider : 'No feed'}
        </span>
      </section>
      </header>

      <TradingSessionTabs
        tabs={tabs}
        activeTabId={activeTabId}
        canAdd={tabs.length < MAX_TRADING_TABS}
        getTabLabel={sessionTabLabel}
        onSelect={setActiveTab}
        onAdd={createTab}
        onClose={closeTabSession}
      />

      <TradingSymbolSearch
        open={symbolSearchOpen}
        query={symbolQuery}
        instruments={[...(instruments.data ?? []), ...symbolSearchResults]}
        activeInstrumentId={symbolSearchTargetInstrument?.instrument_id ?? symbolSearchTarget.instrumentId}
        loading={symbolSearchLoading}
        formulaPreview={formulaResolution}
        onQueryChange={setSymbolQuery}
        onSelect={(match) => applySymbolMatch(match, [match])}
        onSelectFormula={() => applyFormulaResolution(formulaResolution)}
        onClose={closeSymbolSearch}
      />
      <TradingAlertToastLayer />

      <div className="trading-body">
        <TradingDrawingTools selectedTool={drawingTool} onSelect={setDrawingTool} />
        <div className="trading-chart-column">
          <section className="trading-chart-shell" aria-label="Trading chart workspace">
            <TradingChartGrid
              paperAccountId={paperAccountId}
              onOpenSymbolSearch={openSymbolSearch}
              onOpenPineScript={openPineEditor}
              onOpenMarketDataSettings={() => { void navigate({ to: '/settings', search: { category: 'trading-market-data' } }); }}
            />
          </section>
          {workspaceHydrated && panels.bottom && !toolPanel ? (
            <TradingTerminalDock
              instrumentId={activeChart.instrumentId}
              bindingId={selectedBinding?.binding_id ?? activeChart.bindingId}
              preferredAccountId={paperAccountId}
              onAccountChange={setPaperAccountId}
              onSelectAlert={navigateToAlert}
            />
          ) : null}
          {toolPanel ? (
            <section className={`trading-tool-drawer${toolPanelFullscreen ? ' is-fullscreen' : ''}`} aria-label="Trading analysis tool">
              <header>
                <strong>{toolPanel === 'scanner'
                  ? 'Market scanner'
                  : toolPanel === 'replay'
                    ? 'Replay & backtest'
                    : toolPanel === 'strategies'
                      ? 'Automated strategies'
                      : 'AI market research'}</strong>
                <div className="trading-tool-drawer-actions">
                  <button type="button" onClick={() => setToolPanelFullscreen((value) => !value)} aria-pressed={toolPanelFullscreen} aria-label={toolPanelFullscreen ? 'Restore analysis tool' : 'Fullscreen analysis tool'}>{toolPanelFullscreen ? 'Restore' : 'Fullscreen'}</button>
                  <button type="button" onClick={() => { setToolPanelFullscreen(false); setToolPanel(null); }} aria-label="Close analysis tool">×</button>
                </div>
              </header>
              <div>
                {toolPanel === 'scanner' ? <TradingScannerPanel instruments={instruments.data ?? []} /> : null}
                {toolPanel === 'replay' ? (
                  <TradingReplayPanel instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} interval={activeChart.interval} />
                ) : null}
                {toolPanel === 'strategies' ? <TradingStrategiesPanel /> : null}
                {toolPanel === 'research' ? (
                  <TradingResearchPanel instrumentId={activeChart.instrumentId} bindingId={selectedBinding?.binding_id ?? activeChart.bindingId} interval={activeChart.interval} />
                ) : null}
              </div>
            </section>
          ) : null}
        </div>
        {workspaceHydrated ? (
          <div className={`trading-right-dock ${panels.right ? 'is-expanded' : 'is-collapsed'}`}>
            {panels.right ? (
              <TradingSidePanel
                sessionId={activeTabId}
                instruments={visibleInstruments}
                activeInstrumentId={activeChart.instrumentId}
                bindingId={selectedBinding?.binding_id ?? activeChart.bindingId}
                providerBindings={providerBindings}
                interval={activeChart.interval}
                selectedTab={sidePanelTab}
                onTabChange={setSidePanelTab}
                paperAccountId={paperAccountId}
                onPaperAccountChange={setPaperAccountId}
                indicators={activeChart.indicators}
                pineIndicatorId={pineIndicatorId}
                onPineIndicatorChange={setPineIndicatorId}
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
                onSelectAlert={navigateToAlert}
                onSetIndicators={(next) => setIndicators(activeChartId, next)}
                onOpenPineScript={openPineEditor}
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

    </main>
  );
}
