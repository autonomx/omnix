import { useQueries, useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PriceScaleMode, type IChartApi } from 'lightweight-charts';
import { TradingChartAlertOverlay } from './TradingChartAlertOverlay';
import { TradingPositionOverlay } from './TradingPositionOverlay';
import { TradingChartContextMenu } from './TradingChartContextMenu';
import { TradingPriceScaleMenu, defaultTradingPriceScaleMenuState, type TradingPriceScaleMenuState } from './TradingPriceScaleMenu';
import { tradingApi } from './tradingApi';
import { DEFAULT_TRADING_RIGHT_OFFSET, TRADING_CHART_TYPE_OPTIONS, TradingChartAdapter, type TradingChartType, type TradingComparisonData, type TradingIndicatorPaneGeometry, type TradingIndicatorSelection } from './chart/chartAdapter';
import type { TradingChartSynchronization } from './chart/chartSynchronization';
import { TradingDrawingOverlay, type ChartAlertPlacement } from './drawings/TradingDrawingOverlay';
import './drawings/TradingDrawingOverlay.css';
import { useTradingDrawings } from './drawings/useTradingDrawings';
import { indicatorUsesSeparatePane, type CoreIndicatorId, type CoreIndicatorInstance, type IndicatorOutput } from './indicators/coreIndicators';
import { TradingIndicatorScheduler } from './indicators/indicatorScheduler';
import { tradingStreamHub, type TradingStreamStatus } from './streaming/tradingStreamHub';
import { useTradingStore, type TradingIndicatorMove } from './tradingStore';
import { useTradingReplayStore } from './tradingReplayStore';
import type { BarsResponse, MarketBar, TradingAlertIndicatorId, TradingStreamMessage } from './tradingTypes';
import { TradingIndicatorPaneControls } from './TradingIndicatorPaneControls';
import { TradingIndicatorObjectToolbar } from './TradingIndicatorObjectToolbar';
import { TradingIndicatorSettings } from './TradingIndicatorSettings';
import { TradingIndicatorBackgroundOverlay } from './TradingIndicatorBackgroundOverlay';
import { TradingVolumeProfileOverlay } from './TradingVolumeProfileOverlay';
import { TradingYAxisControls } from './TradingYAxisControls';
import { TradingCompareSymbolDialog } from './TradingCompareSymbolDialog';
import { isTradingFormulaInstrumentId } from './tradingFormula';
import { TRADING_COMPARISON_COLORS, type TradingComparison } from './tradingComparisons';
import './TradingChartOverlayLayout.css';
import './TradingChartRangeTooltip.css';
import { OMNIX_APPEARANCE_CHANGE_EVENT } from '../settings/appearanceEffects';
import {
  intervalCompactLabel,
  isIntervalAvailable,
  tradingIntervalMinutes,
} from './tradingIntervals';

type TradingContextMenuState = ChartAlertPlacement & {
  contextIndicatorId?: CoreIndicatorId;
};

function isAlertIndicatorId(id: CoreIndicatorId): id is TradingAlertIndicatorId {
  return id === 'sma'
    || id === 'ema'
    || id === 'rsi'
    || id === 'macd'
    || id === 'bollinger'
    || id === 'atr'
    || id === 'vwap'
    || id === 'stochastic-rsi';
}

const indicatorContextNames: Partial<Record<CoreIndicatorId, string>> = {
  atr: 'ATR',
  bollinger: 'Bollinger Bands',
  'bull-market-band': 'Bull Market Support Band',
  'death-cross': 'Death Cross',
  ema: 'EMA',
  'ema-stack': 'EMA Stack',
  'fair-value-gap': 'Fair Value Gap',
  'golden-cross': 'Golden Cross',
  'ideal-bb': 'IDEAL BB',
  'log-macd': 'Log MACD',
  'macd-dema': 'MACD DEMA',
  macd: 'MACD',
  rsi: 'RSI',
  'rsi-divergence': 'RSI Divergence',
  sma: 'SMA',
  'stochastic-rsi': 'Stoch RSI',
  'swing-liquidity': 'Swing Levels and Liquidity',
  'volume-profile': 'Volume Profile',
  vwap: 'VWAP',
};

function indicatorContextLabel(indicator: CoreIndicatorInstance): string {
  const name = indicatorContextNames[indicator.id] ?? indicator.id.toUpperCase();
  if (indicator.id === 'stochastic-rsi') {
    return `${name} (${indicator.fastPeriod ?? 3}, ${indicator.signalPeriod ?? 3}, ${indicator.period}, ${indicator.period}, close)`;
  }
  if (indicator.id === 'macd' || indicator.id === 'log-macd' || indicator.id === 'macd-dema') {
    return `${name} (${indicator.fastPeriod ?? 12}, ${indicator.slowPeriod ?? 26}, ${indicator.signalPeriod ?? 9}, close)`;
  }
  if (indicator.id === 'bollinger') return `${name} (${indicator.period}, ${indicator.standardDeviations ?? 2}, close)`;
  if (indicator.id === 'death-cross' || indicator.id === 'golden-cross') {
    return `${name} (${indicator.fastPeriod ?? 50}, ${indicator.slowPeriod ?? 200}, close)`;
  }
  if (indicator.id === 'bull-market-band') {
    return `${name} (${indicator.fastPeriod ?? 20}W SMA, ${indicator.slowPeriod ?? 21}W EMA)`;
  }
  return `${name} (${indicator.period}, close)`;
}

const ranges = [
  { label: '1D', days: 1, interval: '1m', tooltip: '1 day in 1 minute intervals' },
  { label: '5D', days: 5, interval: '5m', tooltip: '5 days in 5 minute intervals' },
  { label: '1M', days: 30, interval: '30m', tooltip: '1 month in 30 minute intervals' },
  { label: '3M', days: 90, interval: '1h', tooltip: '3 months in 1 hour intervals' },
  { label: '6M', days: 180, interval: '2h', tooltip: '6 months in 2 hour intervals' },
  { label: 'YTD', days: 250, interval: '1d', tooltip: 'Year to date in 1 day intervals' },
  { label: '1Y', days: 365, interval: '1d', tooltip: '1 year in 1 day intervals' },
  { label: '5Y', days: 1_825, interval: '1w', tooltip: '5 years in 1 week intervals' },
  { label: 'All', days: null, interval: '1mo', tooltip: 'All available data in 1 month intervals' },
] as const;

const rightOffsetStorageKey = 'omnix.trading.chart.right-offset';
const rightOffsetOptions = [0, 5, DEFAULT_TRADING_RIGHT_OFFSET, 20, 50] as const;
const Y_AXIS_DRAG_ZOOM_SENSITIVITY = 2;

function readTradingRightOffset(): number {
  if (typeof window === 'undefined') return DEFAULT_TRADING_RIGHT_OFFSET;
  try {
    const stored = window.localStorage.getItem(rightOffsetStorageKey);
    if (stored === null) return DEFAULT_TRADING_RIGHT_OFFSET;
    const value = Number(stored);
    return rightOffsetOptions.includes(value as typeof rightOffsetOptions[number])
      ? value
      : DEFAULT_TRADING_RIGHT_OFFSET;
  } catch {
    return DEFAULT_TRADING_RIGHT_OFFSET;
  }
}

function normalizeStreamBar(
  message: Extract<TradingStreamMessage, { type: 'bar' }>,
  provider: string,
  ingestionRevision: number,
): MarketBar {
  return {
    instrument_id: message.bar.instrument_id,
    interval: message.bar.interval,
    start_time: message.bar.start_time,
    end_time: message.bar.end_time,
    open: message.bar.open,
    high: message.bar.high,
    low: message.bar.low,
    close: message.bar.close,
    volume: message.bar.volume,
    is_final: message.bar.is_final,
    adjustment_mode: 'raw',
    session: '24x7',
    provider,
    provider_event_id: message.bar.provider_event_id,
    provider_sequence: message.bar.provider_sequence,
    ingestion_revision: ingestionRevision,
    received_at: new Date().toISOString(),
  };
}

function downloadDataUrl(dataUrl: string, filename: string): void {
  const anchor = document.createElement('a');
  anchor.href = dataUrl;
  anchor.download = filename;
  anchor.click();
}

function price(value?: string | null): string {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return String(value ?? '—');
  const digits = Math.abs(parsed) >= 1_000 ? 2 : Math.abs(parsed) >= 1 ? 4 : 6;
  return parsed.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function convertedPrice(value: string | number | null | undefined, multiplier: number): string {
  const parsed = Number(value ?? 0);
  return price(Number.isFinite(parsed) ? String(parsed * multiplier) : null);
}

function intervalMinutes(interval: string): number {
  return tradingIntervalMinutes(interval) ?? 1_440;
}

function intervalLabel(interval: string): string {
  return intervalCompactLabel(interval);
}

function closestSupportedInterval(target: string, supported: readonly string[]): string {
  if (supported.length === 0 || supported.includes(target)) return target;
  const targetMinutes = intervalMinutes(target);
  return [...supported].sort((left, right) => (
    Math.abs(intervalMinutes(left) - targetMinutes) - Math.abs(intervalMinutes(right) - targetMinutes)
  ))[0] ?? target;
}

function applyVisibleRange(chart: IChartApi, days: number | null, total: number, interval: string, rightOffset = DEFAULT_TRADING_RIGHT_OFFSET): void {
  if (total === 0) return;
  const safeRightOffset = Math.max(0, Math.min(100, Math.round(rightOffset)));
  if (days === null) {
    chart.timeScale().setVisibleLogicalRange({
      from: -0.5,
      to: total - 0.5 + safeRightOffset,
    });
    return;
  }
  const requested = Math.max(1, Math.ceil(days * 1_440 / intervalMinutes(interval)));
  const count = Math.min(total, requested);
  chart.timeScale().setVisibleLogicalRange({
    from: Math.max(-0.5, total - count - 0.5),
    to: total - 0.5 + safeRightOffset,
  });
}

function comparisonPercent(bars: readonly MarketBar[]): string {
  const first = Number(bars[0]?.close);
  const last = Number(bars.at(-1)?.close);
  if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) return '—';
  return `${((last / first - 1) * 100).toFixed(2)}%`;
}

const comparisonCurrencyNames: Record<string, string> = {
  BTC: 'Bitcoin',
  ETH: 'Ethereum',
  SOL: 'Solana',
  USD: 'U.S. Dollar',
  USDT: 'Tether',
  USDC: 'USD Coin',
};

function comparisonLabel(instrument: { display_symbol: string; venue: string; asset_class?: string | null; base_currency?: string | null; quote_currency?: string | null } | undefined, fallback: string): string {
  if (!instrument) return fallback;
  if (instrument.asset_class === 'crypto') {
    const base = comparisonCurrencyNames[instrument.base_currency ?? ''] ?? instrument.base_currency ?? instrument.display_symbol;
    const quote = comparisonCurrencyNames[instrument.quote_currency ?? ''] ?? instrument.quote_currency ?? 'U.S. Dollar';
    return `${base} / ${quote} · ${instrument.venue}`;
  }
  return `${instrument.display_symbol} · ${instrument.venue}`;
}

function chartHistoryLimit(
  instrumentId: string,
  interval: string,
  indicators: readonly CoreIndicatorInstance[],
): number {
  const needsExtendedHistory = indicators.some((indicator) => indicator.enabled && indicator.id === 'bull-market-band');
  if (instrumentId.startsWith('index:CRYPTOCAP:') && interval === '1d') return 5_000;
  if (instrumentId.startsWith('crypto:BINANCE:') && (['1d', '1w'].includes(interval) || needsExtendedHistory)) return 5_000;
  if (instrumentId.startsWith('equity:') && interval === '1d') return 2_000;
  return 1_000;
}

type ComparisonBarsResponse = BarsResponse & { historySourceInstrumentId?: string };

function longHistoryEquivalent(instrumentId: string, interval: string): string | null {
  if (!['1d', '1w'].includes(interval)) return null;
  const match = /^crypto:([^:]+):spot:([^:]+)-USD$/i.exec(instrumentId);
  if (!match) return null;
  return `crypto:${match[1]}:spot:${match[2]}-USDT`;
}

function firstBarTime(response: BarsResponse): number {
  const value = Date.parse(response.bars[0]?.start_time ?? '');
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
}

async function comparisonBars(
  instrumentId: string,
  interval: string,
  limit: number,
): Promise<ComparisonBarsResponse> {
  const selected = await tradingApi.bars(instrumentId, interval, limit);
  const equivalent = longHistoryEquivalent(instrumentId, interval);
  if (!equivalent || equivalent === instrumentId) return selected;
  try {
    const candidate = await tradingApi.bars(equivalent, interval, limit);
    if (candidate.bars.length > selected.bars.length && firstBarTime(candidate) < firstBarTime(selected)) {
      return { ...selected, bars: candidate.bars, historySourceInstrumentId: candidate.instrument.instrument_id };
    }
  } catch {
    // The selected instrument remains a valid comparison if its equivalent
    // long-history market is unavailable.
  }
  return selected;
}

export function TradingChartPanel({
  chartId,
  chartNumber,
  instrumentId,
  bindingId,
  interval,
  chartType,
  indicators,
  comparisons,
  active,
  chartFocusMode,
  onActivate,
  onChartFocusChange,
  onOpenSymbolSearch,
  onChangeInterval,
  onChangeChartType,
  onToggleIndicator,
  onClearIndicators,
  onToggleIndicatorVisibility,
  onUpdateIndicator,
  onMoveIndicator,
  onUpdateComparisons,
  onOpenPineScript,
  onOpenMarketDataSettings,
  synchronization,
  paperAccountId,
}: {
  chartId: string;
  chartNumber: number;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  chartType: TradingChartType;
  indicators: CoreIndicatorInstance[];
  comparisons: TradingComparison[];
  active: boolean;
  chartFocusMode: boolean;
  onActivate: () => void;
  onChartFocusChange: (focused: boolean) => void;
  onOpenSymbolSearch: () => void;
  onChangeInterval: (interval: string) => void;
  onChangeChartType: (chartType: TradingChartType) => void;
  onToggleIndicator: (id: CoreIndicatorId) => void;
  onClearIndicators: () => void;
  onToggleIndicatorVisibility: (id: CoreIndicatorId) => void;
  onUpdateIndicator: (id: CoreIndicatorId, patch: Partial<CoreIndicatorInstance>) => void;
  onMoveIndicator: (id: CoreIndicatorId, direction: TradingIndicatorMove) => void;
  onUpdateComparisons: (comparisons: TradingComparison[]) => void;
  onOpenPineScript: (id: CoreIndicatorId) => void;
  onOpenMarketDataSettings?: () => void;
  synchronization: TradingChartSynchronization;
  paperAccountId?: string | null;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const adapterRef = useRef<TradingChartAdapter | null>(null);
  const onActivateRef = useRef(onActivate);
  const barsRef = useRef<MarketBar[]>([]);
  const allBarsRef = useRef<MarketBar[]>([]);
  const replayWasVisibleRef = useRef(false);
  const fittedBarsKeyRef = useRef<string | null>(null);
  const streamDataKeyRef = useRef<string | null>(null);
  const streamRevisionRef = useRef(1);
  const previousIntervalRef = useRef(interval);
  const pendingIntervalScrollRef = useRef(false);
  const [, forceLiveRender] = useState(0);
  const selectedRangeRef = useRef<number | null | undefined>(undefined);
  const pendingRangeIntervalRef = useRef<string | null>(null);
  const indicatorsRef = useRef<CoreIndicatorInstance[]>(indicators);
  const indicatorSchedulerRef = useRef<TradingIndicatorScheduler | null>(null);
  const indicatorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const setDrawingTool = useTradingStore((state) => state.setDrawingTool);
  const drawingSnapMode = useTradingStore((state) => state.drawingSnapMode);
  const replayMode = useTradingStore((state) => state.replayMode);
  const replaySessionId = useTradingStore((state) => state.replaySessionId);
  const setReplayMode = useTradingStore((state) => state.setReplayMode);
  const restartReplaySession = useTradingStore((state) => state.restartReplaySession);
  const setReplayBar = useTradingReplayStore((state) => state.setBar);
  const clearReplayState = useTradingReplayStore((state) => state.clear);
  const drawings = useTradingDrawings(instrumentId);
  const selectedDrawing = drawings.state.drawings.find((drawing) => drawing.drawingId === drawings.state.selectedId) ?? null;
  const [adapter, setAdapter] = useState<TradingChartAdapter | null>(null);
  const [streamStatus, setStreamStatus] = useState<TradingStreamStatus | 'replay'>('connecting');
  const [streamError, setStreamError] = useState<string | null>(null);
  const [indicatorError, setIndicatorError] = useState<string | null>(null);
  const [alertPlacement, setAlertPlacement] = useState<ChartAlertPlacement | null>(null);
  const [contextMenu, setContextMenu] = useState<TradingContextMenuState | null>(null);
  const [priceScaleMenuOpen, setPriceScaleMenuOpen] = useState(false);
  const [priceScaleSettings, setPriceScaleSettings] = useState<TradingPriceScaleMenuState>(defaultTradingPriceScaleMenuState);
  const [priceScaleCurrency, setPriceScaleCurrency] = useState('USD');
  const [priceScaleHovered, setPriceScaleHovered] = useState(false);
  const [tableVisible, setTableVisible] = useState(false);
  const [objectTreeVisible, setObjectTreeVisible] = useState(false);
  const [settingsVisible, setSettingsVisible] = useState(false);
  const [cursorLocked, setCursorLocked] = useState(false);
  const [chartPanning, setChartPanning] = useState(false);
  const [panningIndicatorPane, setPanningIndicatorPane] = useState<string | null>(null);
  const [indicatorPaneGeometry, setIndicatorPaneGeometry] = useState<TradingIndicatorPaneGeometry[]>([]);
  const [indicatorOutputs, setIndicatorOutputs] = useState<IndicatorOutput[]>([]);
  const [indicatorLegendCollapsed, setIndicatorLegendCollapsed] = useState(false);
  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [hoveredIndicatorPane, setHoveredIndicatorPane] = useState<CoreIndicatorId | null>(null);
  const [resizingIndicatorPane, setResizingIndicatorPane] = useState<CoreIndicatorId | null>(null);
  const [settingsIndicator, setSettingsIndicator] = useState<CoreIndicatorInstance | null>(null);
  const [selectedIndicator, setSelectedIndicator] = useState<TradingIndicatorSelection | null>(null);
  const [selectedRangeLabel, setSelectedRangeLabel] = useState('All');
  const [rightOffset, setRightOffset] = useState(readTradingRightOffset);
  const [replayStartIndex, setReplayStartIndex] = useState<number | null>(null);
  const [replayCursorIndex, setReplayCursorIndex] = useState<number | null>(null);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState('1');
  const [replayMarkerX, setReplayMarkerX] = useState<number | null>(null);
  const [replaySelectionIndex, setReplaySelectionIndex] = useState<number | null>(null);
  const [replaySelectionX, setReplaySelectionX] = useState<number | null>(null);
  const [minimizedIndicators, setMinimizedIndicators] = useState<Set<CoreIndicatorId>>(() => new Set());
  const minimizedIndicatorsRef = useRef<Set<CoreIndicatorId>>(new Set());
  const [fullscreenIndicator, setFullscreenIndicator] = useState<CoreIndicatorId | null>(null);
  const fullscreenIndicatorRef = useRef<CoreIndicatorId | null>(null);
  const [fullscreenMainPane, setFullscreenMainPane] = useState(false);
  const fullscreenMainPaneRef = useRef(false);
  const indicatorResizeRef = useRef<{ id: CoreIndicatorId; edge: 'top' | 'bottom'; pointerId: number; lastY: number; target: HTMLDivElement } | null>(null);

  useEffect(() => {
    onActivateRef.current = onActivate;
  }, [onActivate]);

  const clearAlertPlacement = useCallback(() => setAlertPlacement(null), []);
  const refreshIndicatorPanes = useCallback((targetAdapter?: TradingChartAdapter | null) => {
    if (!targetAdapter) {
      setIndicatorPaneGeometry([]);
      return;
    }
    try {
      setIndicatorPaneGeometry(targetAdapter.indicatorPaneGeometry());
    } catch {
      setIndicatorPaneGeometry([]);
    }
  }, []);
  const scheduleIndicators = useCallback((delay = 0) => {
    if (indicatorTimerRef.current) clearTimeout(indicatorTimerRef.current);
    indicatorTimerRef.current = setTimeout(() => {
      indicatorTimerRef.current = null;
      const scheduler = indicatorSchedulerRef.current;
      const targetAdapter = adapterRef.current;
      if (!scheduler || !targetAdapter) return;
      void scheduler.calculate(barsRef.current, indicatorsRef.current)
        .then((outputs) => {
          if (outputs && adapterRef.current === targetAdapter) {
            targetAdapter.setIndicatorOutputs(outputs);
            setIndicatorOutputs(outputs);
            if (fullscreenIndicatorRef.current) {
              targetAdapter.setIndicatorPaneFullscreen(fullscreenIndicatorRef.current);
            } else if (fullscreenMainPaneRef.current) {
              targetAdapter.setMainPaneFullscreen(true);
            } else {
              for (const indicator of indicatorsRef.current) {
                if (indicatorUsesSeparatePane(indicator.id)) {
                  targetAdapter.setIndicatorPaneMinimized(indicator.id, minimizedIndicatorsRef.current.has(indicator.id));
                }
              }
            }
            refreshIndicatorPanes(targetAdapter);
            window.requestAnimationFrame(() => {
              if (adapterRef.current !== targetAdapter) return;
              if (fullscreenIndicatorRef.current) {
                targetAdapter.setIndicatorPaneFullscreen(fullscreenIndicatorRef.current);
              } else if (fullscreenMainPaneRef.current) {
                targetAdapter.setMainPaneFullscreen(true);
              } else {
                for (const indicator of indicatorsRef.current) {
                  if (indicatorUsesSeparatePane(indicator.id)) {
                    targetAdapter.setIndicatorPaneMinimized(indicator.id, minimizedIndicatorsRef.current.has(indicator.id));
                  }
                }
              }
              refreshIndicatorPanes(targetAdapter);
              window.requestAnimationFrame(() => refreshIndicatorPanes(targetAdapter));
            });
            setIndicatorError(null);
          }
        })
        .catch((error) => setIndicatorError(error instanceof Error ? error.message : String(error)));
    }, delay);
  }, [refreshIndicatorPanes]);
  const historyLimit = chartHistoryLimit(instrumentId, interval, indicators);
  const chartQuery = useQuery({
    queryKey: ['trading', 'bars', instrumentId, bindingId, interval, historyLimit],
    queryFn: () => tradingApi.bars(instrumentId, interval, historyLimit, bindingId),
    enabled: Boolean(instrumentId),
    staleTime: 15_000,
  });
  const comparisonQueries = useQueries({
    queries: comparisons.map((comparison) => {
      const comparisonLimit = chartHistoryLimit(comparison.instrumentId, interval, []);
      return {
        queryKey: ['trading', 'comparison-bars-v2', comparison.instrumentId, interval, comparisonLimit, comparison.placement],
        queryFn: () => comparisonBars(comparison.instrumentId, interval, comparisonLimit),
        enabled: Boolean(comparison.instrumentId),
        staleTime: 15_000,
      };
    }),
  });
  const comparisonRenderData = useMemo<TradingComparisonData[]>(() => comparisons.map((comparison, index) => {
    const result = comparisonQueries[index];
    return {
      instrumentId: comparison.instrumentId,
      label: comparisonLabel(result?.data?.instrument, comparison.instrumentId),
      placement: comparison.placement,
      color: TRADING_COMPARISON_COLORS[index % TRADING_COMPARISON_COLORS.length],
      visible: comparison.visible !== false,
      bars: (result?.data?.bars ?? []) as MarketBar[],
    };
  }), [comparisons, comparisonQueries]);
  const sourceCurrency = chartQuery.data?.instrument.quote_currency?.toUpperCase() ?? 'USD';
  const supportsCurrencyConversion = /^[A-Z]{3}$/u.test(sourceCurrency);
  const currencyRateQuery = useQuery({
    queryKey: ['trading', 'currency-rate', sourceCurrency, priceScaleCurrency],
    queryFn: () => tradingApi.currencyRate(sourceCurrency, priceScaleCurrency),
    enabled: supportsCurrencyConversion
      && Boolean(sourceCurrency && priceScaleCurrency && sourceCurrency !== priceScaleCurrency),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const priceScaleMultiplier = !supportsCurrencyConversion || sourceCurrency === priceScaleCurrency
    ? 1
    : currencyRateQuery.data?.rate ?? 1;

  useEffect(() => {
    setPriceScaleCurrency(sourceCurrency);
  }, [sourceCurrency, instrumentId]);

  useEffect(() => {
    if (!adapter) return;
    adapter.setPriceScaleMultiplier(priceScaleMultiplier);
  }, [adapter, priceScaleMultiplier]);

  useEffect(() => {
    if (!adapter) return;
    adapter.setComparisonData(comparisonRenderData);
  }, [adapter, comparisonRenderData]);

  useEffect(() => {
    if (!adapter) return;
    adapter.setRightOffset(rightOffset);
  }, [adapter, rightOffset]);

  useEffect(() => {
    if (!adapter) {
      setSelectedIndicator(null);
      return;
    }
    const unregister = adapter.onIndicatorClick((selection) => {
      onActivateRef.current();
      setSelectedIndicator(selection);
    });
    return () => {
      unregister();
      setSelectedIndicator(null);
    };
  }, [adapter]);

  useEffect(() => {
    if (selectedIndicator && !indicators.some((indicator) => indicator.id === selectedIndicator.id && indicator.enabled)) {
      setSelectedIndicator(null);
    }
  }, [indicators, selectedIndicator]);

  useEffect(() => {
    if (!selectedIndicator) return;
    const handleOutsidePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('.trading-indicator-object-toolbar')) return;
      setSelectedIndicator(null);
    };
    document.addEventListener('pointerdown', handleOutsidePointerDown, true);
    return () => document.removeEventListener('pointerdown', handleOutsidePointerDown, true);
  }, [selectedIndicator]);

  const replayVisible = replayMode && active && replayCursorIndex !== null;

  useEffect(() => {
    if (!hostRef.current) return;
    const next = new TradingChartAdapter(hostRef.current, chartType);
    const scheduler = new TradingIndicatorScheduler();
    adapterRef.current = next;
    indicatorSchedulerRef.current = scheduler;
    fittedBarsKeyRef.current = null;
    streamDataKeyRef.current = null;
    streamRevisionRef.current = 1;
    selectedRangeRef.current = undefined;
    pendingRangeIntervalRef.current = null;
    setSelectedRangeLabel('All');
    setPriceScaleMenuOpen(false);
    setPriceScaleSettings(defaultTradingPriceScaleMenuState);
    fullscreenIndicatorRef.current = null;
    setFullscreenIndicator(null);
    fullscreenMainPaneRef.current = false;
    setFullscreenMainPane(false);
    setAdapter(next);
    setIndicatorOutputs([]);
    setIndicatorPaneGeometry([]);
    const unregister = synchronization.register(chartId, next);
    return () => {
      unregister();
      if (indicatorTimerRef.current) clearTimeout(indicatorTimerRef.current);
      indicatorTimerRef.current = null;
      scheduler.destroy();
      next.destroy();
      indicatorSchedulerRef.current = null;
      adapterRef.current = null;
      setAdapter(null);
      setIndicatorOutputs([]);
    };
  }, [chartId, synchronization]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !adapter) return;
    let pan: { pointerId: number; lastX: number; lastY: number; paneY: number; paneId: string | null; mode: 'chart-pan' | 'price-scale' | 'price-pan' } | null = null;
    const insideHost = (event: PointerEvent) => event.target instanceof Node && host.contains(event.target);
    const pointerDown = (event: PointerEvent) => {
      const target = event.target;
      const element = target instanceof Element ? target : null;
      if (!element?.closest('.trading-chart-context-menu')) setContextMenu(null);
      if (!element?.closest('.trading-indicator-object-toolbar')) setSelectedIndicator(null);
      if (!element?.closest('[data-drawing-id], .trading-drawing-manager, .trading-chart-context-menu')) drawings.select(null);
      if (!insideHost(event)) return;
      const isPrimaryPan = event.button === 0 && drawingTool === 'cursor';
      const isMiddlePan = event.button === 1;
      if ((!isPrimaryPan && !isMiddlePan) || event.pointerType === 'touch') return;
      const bounds = host.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const paneY = event.clientY - bounds.top;
      const onPriceScale = adapter.isPriceScaleCoordinate(x);
      // Replay owns the chart canvas for bar selection/playback, but the
      // price scale remains an independent viewport control. Keep its
      // TradingView-style drag zoom available while replay is active.
      if (replayMode && active && !onPriceScale) return;
      pan = {
        pointerId: event.pointerId,
        lastX: event.clientX,
        lastY: event.clientY,
        paneY,
        paneId: onPriceScale ? null : adapter.indicatorPaneIdAtCoordinate(paneY),
        mode: onPriceScale ? 'price-scale' : event.shiftKey ? 'price-pan' : 'chart-pan',
      };
      setChartPanning(!onPriceScale);
      setPanningIndicatorPane(pan.paneId);
      host.setPointerCapture(event.pointerId);
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    };
    const pointerMove = (event: PointerEvent) => {
      if (!pan || pan.pointerId !== event.pointerId) return;
      const deltaX = event.clientX - pan.lastX;
      const deltaY = event.clientY - pan.lastY;
      const bounds = host.getBoundingClientRect();
      if (pan.mode === 'price-scale') adapter.zoomPriceScaleAtCoordinate(event.clientY - bounds.top, deltaY * Y_AXIS_DRAG_ZOOM_SENSITIVITY);
      else if (pan.mode === 'price-pan') adapter.panPriceScaleByPixelsAtCoordinate(pan.paneY, -deltaY);
      else {
        // TradingView-style chart dragging: horizontal motion pans time and
        // vertical motion translates the visible price range at the same time.
        adapter.panTimeByPixels(deltaX);
        // Invert the screen delta so dragging upward moves the visible chart
        // downward, matching the requested TradingView-style y-axis feel.
        adapter.panPriceScaleByPixelsAtCoordinate(pan.paneY, -deltaY);
      }
      pan.lastX = event.clientX;
      pan.lastY = event.clientY;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    };
    const pointerUp = (event: PointerEvent) => {
      if (!pan || pan.pointerId !== event.pointerId) return;
      pan = null;
      setChartPanning(false);
      setPanningIndicatorPane(null);
      if (host.hasPointerCapture(event.pointerId)) host.releasePointerCapture(event.pointerId);
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    };
    const lostPointerCapture = () => {
      pan = null;
      setChartPanning(false);
      setPanningIndicatorPane(null);
    };
    window.addEventListener('pointerdown', pointerDown, true);
    window.addEventListener('pointermove', pointerMove, true);
    window.addEventListener('pointerup', pointerUp, true);
    window.addEventListener('pointercancel', pointerUp, true);
    host.addEventListener('lostpointercapture', lostPointerCapture, true);
    return () => {
      window.removeEventListener('pointerdown', pointerDown, true);
      window.removeEventListener('pointermove', pointerMove, true);
      window.removeEventListener('pointerup', pointerUp, true);
      window.removeEventListener('pointercancel', pointerUp, true);
      host.removeEventListener('lostpointercapture', lostPointerCapture, true);
      pan = null;
      setChartPanning(false);
      setPanningIndicatorPane(null);
    };
  }, [active, adapter, drawingTool, replayMode]);

  useEffect(() => {
    if (!adapter) return;
    const applyAppearance = () => {
      adapter.setAppearance(document.documentElement.dataset.omnixAppearance === 'light' ? 'light' : 'dark');
    };
    applyAppearance();
    window.addEventListener(OMNIX_APPEARANCE_CHANGE_EVENT, applyAppearance);
    return () => window.removeEventListener(OMNIX_APPEARANCE_CHANGE_EVENT, applyAppearance);
  }, [adapter]);

  useEffect(() => {
    if (previousIntervalRef.current === interval) return;
    previousIntervalRef.current = interval;
    pendingIntervalScrollRef.current = true;
  }, [interval]);

  useEffect(() => {
    const bars = (chartQuery.data?.bars ?? []) as MarketBar[];
    allBarsRef.current = bars;
    const dataKey = chartQuery.data
      ? `${chartQuery.data.instrument.instrument_id}|${chartQuery.data.binding.binding_id}|${chartQuery.data.interval}|${historyLimit}`
      : null;
    if (dataKey !== null && dataKey !== streamDataKeyRef.current) {
      streamDataKeyRef.current = dataKey;
      streamRevisionRef.current = Math.max(
        1,
        ...bars.map((bar) => Number(bar.ingestion_revision) || 1),
      );
    }
    forceLiveRender((value) => value + 1);
    const dataChanged = dataKey !== null && dataKey !== fittedBarsKeyRef.current;
    const replayViewChanged = replayWasVisibleRef.current !== replayVisible;
    replayWasVisibleRef.current = replayVisible;
    // Selecting a replay bar replaces the data with the historical prefix,
    // but must preserve the pre-click logical range. Fitting that prefix would
    // move the selected bar to the right edge instead of leaving it where the
    // user clicked. Fit only when loading new data or returning to live mode.
    const shouldFit = dataChanged || (replayViewChanged && !replayVisible);
    const keepSelectedRange = dataChanged && pendingRangeIntervalRef.current === interval;
    if (dataChanged && !keepSelectedRange) {
      selectedRangeRef.current = undefined;
      setSelectedRangeLabel('All');
    }
    const visibleBars = replayVisible
      ? bars.slice(0, Math.min(bars.length, (replayCursorIndex ?? 0) + 1))
      : bars;
    barsRef.current = visibleBars;
    adapterRef.current?.setBars(visibleBars, shouldFit);
    if (keepSelectedRange && selectedRangeRef.current !== undefined && visibleBars.length > 0 && adapterRef.current) {
      applyVisibleRange(adapterRef.current.api(), selectedRangeRef.current, visibleBars.length, interval, rightOffset);
    }
    if (pendingIntervalScrollRef.current && dataChanged && visibleBars.length > 0 && adapterRef.current) {
      adapterRef.current.scrollToLatest();
      pendingIntervalScrollRef.current = false;
    }
    if (keepSelectedRange) pendingRangeIntervalRef.current = null;
    if (dataKey !== null && bars.length > 0) fittedBarsKeyRef.current = dataKey;
    scheduleIndicators();
  }, [active, chartQuery.data, interval, replayCursorIndex, replayMode, replayStartIndex, replayVisible, rightOffset, scheduleIndicators]);

  useEffect(() => {
    setReplayStartIndex(null);
    setReplayCursorIndex(null);
    setReplayPlaying(false);
    if (replayMode && active) restartReplaySession();
  }, [active, bindingId, instrumentId, interval, replayMode, restartReplaySession]);

  useEffect(() => {
    if (!replayMode || !active) {
      if (!replayMode && active) clearReplayState();
      return;
    }
    setReplayBar(replayCurrentBar);
  }, [active, clearReplayState, replayCursorIndex, replayMode, replaySessionId, setReplayBar]);

  useEffect(() => {
    if (!replayMode || !active) {
      setReplayPlaying(false);
      return;
    }
    if (replayCursorIndex === null || replayCursorIndex >= allBarsRef.current.length - 1) {
      setReplayPlaying(false);
    }
  }, [active, replayCursorIndex, replayMode]);

  useEffect(() => {
    if (!replayPlaying || !replayVisible || replayCursorIndex === null) return;
    const numericSpeed = Math.max(0.25, Math.min(8, Number(replaySpeed) || 1));
    const timer = window.setInterval(() => {
      setReplayCursorIndex((current) => {
        const lastIndex = allBarsRef.current.length - 1;
        if (current === null || current >= lastIndex) {
          setReplayPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, Math.max(100, 1_000 / numericSpeed));
    return () => window.clearInterval(timer);
  }, [replayCursorIndex, replayPlaying, replaySpeed, replayVisible]);

  useEffect(() => {
    adapterRef.current?.setChartType(chartType, barsRef.current);
    if (selectedRangeRef.current !== undefined && barsRef.current.length > 0 && adapterRef.current) {
      applyVisibleRange(adapterRef.current.api(), selectedRangeRef.current, barsRef.current.length, interval, rightOffset);
    }
  }, [chartType, interval, rightOffset]);

  useEffect(() => {
    indicatorsRef.current = indicators;
    scheduleIndicators();
  }, [indicators, scheduleIndicators]);

  useEffect(() => {
    if (!active) return;
    const handleDrawingKeyboard = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]')) return;
      const key = event.key.toLowerCase();
      if ((event.metaKey || event.ctrlKey) && !event.altKey && key === 'z') {
        event.preventDefault();
        event.stopPropagation();
        if (event.shiftKey) drawings.redo();
        else drawings.undo();
        return;
      }
      if (!selectedDrawing || (event.key !== 'Delete' && event.key !== 'Backspace')) return;
      event.preventDefault();
      event.stopPropagation();
      drawings.removeSelected();
    };
    window.addEventListener('keydown', handleDrawingKeyboard);
    return () => window.removeEventListener('keydown', handleDrawingKeyboard);
  }, [active, drawings, selectedDrawing]);

  useEffect(() => {
    const targetAdapter = adapterRef.current;
    if (!targetAdapter) return;
    if (fullscreenIndicator) {
      targetAdapter.setIndicatorPaneFullscreen(fullscreenIndicator);
    } else if (fullscreenMainPane) {
      targetAdapter.setMainPaneFullscreen(true);
    } else {
      for (const indicator of indicators) {
        if (indicatorUsesSeparatePane(indicator.id)) {
          targetAdapter.setIndicatorPaneMinimized(indicator.id, minimizedIndicators.has(indicator.id));
        }
      }
    }
    refreshIndicatorPanes(targetAdapter);
    const frame = window.requestAnimationFrame(() => refreshIndicatorPanes(targetAdapter));
    return () => window.cancelAnimationFrame(frame);
  }, [adapter, fullscreenIndicator, fullscreenMainPane, indicators, minimizedIndicators, refreshIndicatorPanes]);

  useEffect(() => {
    if (!adapter) return;
    const refresh = () => {
      try {
        adapter.refreshIndicatorPaneFullscreen();
      } catch {
        // The adapter may be disposed during a chart switch.
      }
      const frame = window.requestAnimationFrame(() => refreshIndicatorPanes(adapter));
      return frame;
    };
    refresh();
    window.addEventListener('resize', refresh);
    const host = hostRef.current;
    const observer = typeof ResizeObserver === 'undefined' || !host ? null : new ResizeObserver(refresh);
    if (observer && host) observer.observe(host);
    return () => {
      window.removeEventListener('resize', refresh);
      observer?.disconnect();
    };
  }, [adapter, refreshIndicatorPanes]);

  useEffect(() => {
    const resolved = chartQuery.data?.binding;
    if (!instrumentId || !resolved) return;
    if (replayMode && active) {
      setStreamStatus('replay');
      return;
    }
    if (isTradingFormulaInstrumentId(instrumentId)) {
      setStreamStatus('polling');
      const poll = window.setInterval(() => void chartQuery.refetch(), 30_000);
      return () => window.clearInterval(poll);
    }
    setStreamError(null);
    const derivedInterval = !resolved.supported_intervals.includes(interval);
    if (resolved.feed_type !== 'websocket_and_rest' || derivedInterval) {
      setStreamStatus('polling');
      const poll = window.setInterval(() => void chartQuery.refetch(), 30_000);
      return () => window.clearInterval(poll);
    }
    return tradingStreamHub.subscribe(
      chartId,
      instrumentId,
      interval,
      (message) => {
        if (message.type === 'error') {
          // The gateway reports upstream disconnects before the hub retries.
          // Keep those transient transport errors out of the chart overlay;
          // the stream status indicator still shows the reconnect state, and
          // non-transport/configuration errors remain visible.
          if (message.code !== 'stream_failed') setStreamError(message.message);
          return;
        }
        const providerRevision = Number(message.bar.ingestion_revision) || 0;
        const ingestionRevision = Math.max(streamRevisionRef.current + 1, providerRevision);
        streamRevisionRef.current = ingestionRevision;
        const bar = normalizeStreamBar(message, resolved.provider, ingestionRevision);
        if (adapterRef.current?.updateBar(bar)) {
          const index = barsRef.current.findIndex((item) => item.start_time === bar.start_time);
          if (index >= 0) barsRef.current[index] = bar;
          else barsRef.current = [...barsRef.current, bar];
          const allIndex = allBarsRef.current.findIndex((item) => item.start_time === bar.start_time);
          if (allIndex >= 0) allBarsRef.current[allIndex] = bar;
          else allBarsRef.current = [...allBarsRef.current, bar];
          forceLiveRender((value) => value + 1);
          scheduleIndicators(bar.is_final ? 0 : 100);
        }
      },
      (status) => {
        setStreamStatus(status);
        if (status === 'live') setStreamError(null);
        if (status === 'closed' || status === 'error') void chartQuery.refetch();
      },
      resolved.binding_id,
    );
  }, [active, chartId, instrumentId, interval, replayMode, chartQuery.data?.binding.binding_id, scheduleIndicators]);

  const provenance = chartQuery.data?.provenance;
  const resolvedBinding = chartQuery.data?.binding;
  const bars = barsRef.current.length > 0 ? barsRef.current : chartQuery.data?.bars ?? [];
  const latest = bars[bars.length - 1];
  const previous = bars[bars.length - 2];
  const latestClose = Number(latest?.close ?? 0);
  const previousClose = Number(previous?.close ?? latest?.open ?? 0);
  const change = latestClose - previousClose;
  const changePercent = previousClose === 0 ? 0 : change / previousClose * 100;
  const direction = change < 0 ? 'negative' : 'positive';
  const paneIndicators = indicators.filter((indicator) => indicator.enabled && indicatorUsesSeparatePane(indicator.id));
  const indicatorControls = indicators.filter((indicator) => indicator.enabled);
  const legendIndicators = fullscreenMainPane
    ? indicatorControls.filter((indicator) => !indicatorUsesSeparatePane(indicator.id))
    : fullscreenIndicator
      ? indicatorControls.filter((indicator) => indicator.id === fullscreenIndicator)
      : indicatorControls;
  const legendComparisons = fullscreenIndicator ? [] : comparisonRenderData;
  const legendCount = legendIndicators.length + legendComparisons.length;
  const visibleIndicatorOutputs = fullscreenMainPane
    ? indicatorOutputs.filter((output) => output.pane === 0)
    : fullscreenIndicator
      ? indicatorOutputs.filter((output) => output.key.split(':', 1)[0] === fullscreenIndicator)
      : indicatorOutputs;
  const selectedIndicatorConfig = selectedIndicator
    ? indicators.find((indicator) => indicator.id === selectedIndicator.id && indicator.enabled) ?? null
    : null;
  const contextIndicator = contextMenu?.contextIndicatorId
    ? indicators.find((indicator) => indicator.id === contextMenu.contextIndicatorId && indicator.enabled) ?? null
    : null;

  useEffect(() => {
    if (!fullscreenIndicator || paneIndicators.some((indicator) => indicator.id === fullscreenIndicator)) return;
    fullscreenIndicatorRef.current = null;
    setFullscreenIndicator(null);
    adapterRef.current?.setIndicatorPaneFullscreen(null);
  }, [fullscreenIndicator, paneIndicators]);

  useEffect(() => {
    if (chartFocusMode) return;
    if (fullscreenIndicatorRef.current !== null) {
      fullscreenIndicatorRef.current = null;
      setFullscreenIndicator(null);
      adapterRef.current?.setIndicatorPaneFullscreen(null);
    }
    if (fullscreenMainPaneRef.current) {
      fullscreenMainPaneRef.current = false;
      setFullscreenMainPane(false);
      adapterRef.current?.setMainPaneFullscreen(false);
    }
  }, [chartFocusMode]);

  const toggleFullscreen = () => {
    const nextFocused = !chartFocusMode;
    fullscreenIndicatorRef.current = null;
    setFullscreenIndicator(null);
    adapterRef.current?.setIndicatorPaneFullscreen(null);
    fullscreenMainPaneRef.current = nextFocused;
    setFullscreenMainPane(nextFocused);
    if (nextFocused) adapterRef.current?.setMainPaneFullscreen(true);
    else adapterRef.current?.setMainPaneFullscreen(false);
    onChartFocusChange(nextFocused);
  };

  const toggleMinimizedIndicator = (id: CoreIndicatorId) => {
    if (fullscreenIndicatorRef.current === id) return;
    setMinimizedIndicators((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      minimizedIndicatorsRef.current = next;
      return next;
    });
  };

  const resetIndicatorPaneView = (id: CoreIndicatorId) => {
    // Resetting a price scale causes Lightweight Charts to reflow the pane.
    // Clear the hover latch at the same time so the controls remain hover-only
    // after that reflow.
    setHoveredIndicatorPane(null);
    adapterRef.current?.resetIndicatorPaneView(id);
  };

  const toggleFullscreenIndicator = (id: CoreIndicatorId) => {
    const next = fullscreenIndicatorRef.current === id ? null : id;
    fullscreenIndicatorRef.current = next;
    setFullscreenIndicator(next);
    if (next) {
      fullscreenMainPaneRef.current = false;
      setFullscreenMainPane(false);
      adapterRef.current?.setMainPaneFullscreen(false);
      setMinimizedIndicators((current) => {
        const updated = new Set(current);
        updated.delete(id);
        minimizedIndicatorsRef.current = updated;
        return updated;
      });
      adapterRef.current?.setIndicatorPaneFullscreen(next);
      onChartFocusChange(true);
      return;
    }
    fullscreenMainPaneRef.current = false;
    setFullscreenMainPane(false);
    adapterRef.current?.setIndicatorPaneFullscreen(null);
    onChartFocusChange(false);
  };

  const closeIndicator = (id: CoreIndicatorId) => {
    if (fullscreenIndicatorRef.current === id) {
      fullscreenIndicatorRef.current = null;
      setFullscreenIndicator(null);
      adapterRef.current?.setIndicatorPaneFullscreen(null);
      onChartFocusChange(false);
    }
    setSettingsIndicator((current) => current?.id === id ? null : current);
    setMinimizedIndicators((current) => {
      const next = new Set(current);
      next.delete(id);
      minimizedIndicatorsRef.current = next;
      return next;
    });
    onToggleIndicator(id);
  };

  const startIndicatorPaneResize = (event: React.PointerEvent<HTMLDivElement>, id: CoreIndicatorId, edge: 'top' | 'bottom') => {
    if (event.button !== 0 || event.pointerType === 'touch' || fullscreenIndicatorRef.current !== null) return;
    indicatorResizeRef.current = { id, edge, pointerId: event.pointerId, lastY: event.clientY, target: event.currentTarget };
    setResizingIndicatorPane(id);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
  };

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const resize = indicatorResizeRef.current;
      if (!resize || resize.pointerId !== event.pointerId) return;
      const deltaY = event.clientY - resize.lastY;
      resize.lastY = event.clientY;
      adapterRef.current?.resizeIndicatorPaneByPixels(resize.id, resize.edge, deltaY);
      refreshIndicatorPanes(adapterRef.current);
      event.preventDefault();
    };
    const finish = (event: PointerEvent) => {
      const resize = indicatorResizeRef.current;
      if (!resize || resize.pointerId !== event.pointerId) return;
      if (resize.target.hasPointerCapture(event.pointerId)) resize.target.releasePointerCapture(event.pointerId);
      indicatorResizeRef.current = null;
      setResizingIndicatorPane(null);
      event.preventDefault();
    };
    window.addEventListener('pointermove', move, { passive: false });
    window.addEventListener('pointerup', finish, { passive: false });
    window.addEventListener('pointercancel', finish, { passive: false });
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
    };
  }, [refreshIndicatorPanes]);

  const changeRightOffset = (value: string | number) => {
    const parsed = Number(value);
    const next = rightOffsetOptions.includes(parsed as typeof rightOffsetOptions[number])
      ? parsed
      : DEFAULT_TRADING_RIGHT_OFFSET;
    setRightOffset(next);
    selectedRangeRef.current = null;
    setSelectedRangeLabel('All');
    adapterRef.current?.setRightOffset(next);
    adapterRef.current?.fitContent();
    try {
      window.localStorage.setItem(rightOffsetStorageKey, String(next));
    } catch {
      // The setting remains active for the current session when storage is unavailable.
    }
  };

  const showRange = (label: string, days: number | null, requestedInterval: string) => {
    selectedRangeRef.current = days;
    setSelectedRangeLabel(label);
    const supportedIntervals = chartQuery.data?.binding.supported_intervals ?? [];
    const nextInterval = isIntervalAvailable(requestedInterval, supportedIntervals)
      ? requestedInterval
      : closestSupportedInterval(requestedInterval, supportedIntervals);
    pendingRangeIntervalRef.current = interval === nextInterval ? null : nextInterval;
    onChangeInterval(nextInterval);
    const chart = adapterRef.current?.api();
    if (!chart) return;
    if (interval === nextInterval) applyVisibleRange(chart, days, barsRef.current.length, interval, rightOffset);
  };

  const openContextMenu = (point: ChartAlertPlacement, indicatorId?: CoreIndicatorId) => {
    if (!active) onActivate();
    setSelectedIndicator(null);
    const resolvedIndicatorId = indicatorId;
    const resolvedIndicator = resolvedIndicatorId
      ? indicators.find((indicator) => indicator.id === resolvedIndicatorId && indicator.enabled)
      : undefined;
    const alertIndicatorId = resolvedIndicatorId && isAlertIndicatorId(resolvedIndicatorId)
      ? resolvedIndicatorId
      : undefined;
    const stage = hostRef.current?.parentElement;
    const width = stage?.clientWidth ?? 0;
    const height = stage?.clientHeight ?? 0;
    setContextMenu({
      ...point,
      contextIndicatorId: resolvedIndicatorId,
      indicatorId: alertIndicatorId,
      indicatorPeriod: resolvedIndicator?.period,
      x: Math.max(6, Math.min(point.x, Math.max(6, width - 286))),
      y: Math.max(6, Math.min(point.y, Math.max(6, height - 420))),
    });
  };

  const handleStageContextMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const target = event.target as Element;
    if (target.closest('.trading-chart-context-menu, .trading-price-scale-menu, .trading-price-scale-trigger, .trading-chart-alert-editor, .trading-chart-table-view, .trading-chart-object-tree, .trading-chart-settings, .trading-indicator-pane-controls, .trading-indicator-object-toolbar')) return;
    const stage = event.currentTarget;
    const bounds = stage.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    const indicatorId = adapterRef.current?.indicatorPaneIdAtClientY(event.clientY);
    const indicator = indicatorId === null || indicatorId === undefined
      ? undefined
      : paneIndicators.find((item) => item.id === indicatorId);
    if (indicator) {
      const point = adapterRef.current?.drawingPointFromCoordinate(x, y);
      const indicatorValue = adapterRef.current?.indicatorValueFromClientY(indicator.id, event.clientY);
      if (point) openContextMenu({ ...point, price: indicatorValue ?? point.price, x, y, source: 'context-menu' }, indicator.id);
      return;
    }
    const point = adapterRef.current?.drawingPointFromCoordinate(x, y);
    if (point) openContextMenu({ ...point, x, y, source: 'context-menu' });
  };

  const handleStagePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const targetAdapter = adapterRef.current;
    const target = event.target as Element;
    // Drawing and alert tools own the chart pointer. Do not let transient pane
    // hover chrome appear underneath that interaction and intercept placement.
    if (drawingTool !== 'cursor') {
      setHoveredIndicatorPane(null);
    } else if (targetAdapter) {
      const bounds = event.currentTarget.getBoundingClientRect();
      const y = event.clientY - bounds.top;
      const hoveredPane = indicatorPaneGeometry.find((pane) => y >= pane.top && y <= pane.top + pane.height);
      const nextHoveredPane = hoveredPane ? hoveredPane.id as CoreIndicatorId : null;
      setHoveredIndicatorPane((current) => current === nextHoveredPane ? current : nextHoveredPane);
    } else {
      setHoveredIndicatorPane(null);
    }
    if (target.closest('.trading-y-axis-controls')) {
      setPriceScaleHovered(true);
      return;
    }
    if (!targetAdapter) {
      setPriceScaleHovered(false);
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    if (replayMode && active && replayCursorIndex === null && !target.closest('button, input, select, textarea, [role="dialog"]')) {
      const x = event.clientX - bounds.left;
      if (!targetAdapter.isPriceScaleCoordinate(x)) {
        const index = targetAdapter.barIndexAtCoordinate(x, allBarsRef.current.length);
        if (index !== null) setReplaySelectionIndex(index);
      }
    }
    const nextHovered = targetAdapter.isMainPriceScaleCoordinate(event.clientX - bounds.left);
    setPriceScaleHovered((current) => current === nextHovered ? current : nextHovered);
  };

  const handleStagePointerLeave = () => {
    setPriceScaleHovered(false);
    setHoveredIndicatorPane(null);
  };

  const copyContextPrice = () => {
    if (!contextMenu) return;
    void navigator.clipboard?.writeText(String(contextMenu.price));
  };

  const pasteContextPrice = () => {
    if (!contextMenu) return;
    void navigator.clipboard?.readText().then((value) => {
      const pasted = Number(value.trim());
      if (Number.isFinite(pasted)) setAlertPlacement({ ...contextMenu, price: pasted, source: 'context-menu' });
    }).catch(() => undefined);
  };

  const applyChartTemplate = (template: 'default' | 'clean' | 'momentum') => {
    if (template === 'clean') {
      onClearIndicators();
      drawings.removeAll();
      return;
    }
    if (template === 'momentum') {
      for (const id of ['rsi', 'macd'] as CoreIndicatorId[]) {
        if (!indicators.some((indicator) => indicator.id === id && indicator.enabled)) onToggleIndicator(id);
      }
    }
  };

  const contextMenuAlert = () => {
    if (contextMenu?.indicatorId || !contextMenu?.contextIndicatorId) setAlertPlacement(contextMenu);
  };

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    // React delegates wheel events through a passive listener in this setup.
    // Use a native non-passive listener because chart zoom intentionally
    // consumes the wheel event so the page does not scroll underneath it.
    const handleChartWheel = (event: WheelEvent) => {
      const targetAdapter = adapterRef.current;
      if (!targetAdapter) return;
      event.preventDefault();
      event.stopPropagation();
      const bounds = host.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      if (targetAdapter.isPriceScaleCoordinate(x)) {
        targetAdapter.zoomPriceScaleAtCoordinate(y, event.deltaY);
        return;
      }
      if (event.deltaX !== 0) {
        targetAdapter.panTimeByPixels(-event.deltaX);
        return;
      }
      if (event.shiftKey) {
        targetAdapter.zoomPriceScaleAtCoordinate(y, event.deltaY);
        return;
      }
      targetAdapter.zoomAtCoordinate(x, event.deltaY);
    };

    host.addEventListener('wheel', handleChartWheel, { capture: true, passive: false });
    return () => host.removeEventListener('wheel', handleChartWheel, true);
  }, [adapter]);

  const handleReplayStageClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!replayMode || !active || !adapter || allBarsRef.current.length === 0) return;
    // A chart click chooses a new replay start only after the user explicitly
    // enters Select bar mode. Normal clicks during an active replay must not
    // restart the session and discard its simulated positions.
    if (replayCursorIndex !== null) return;
    const target = event.target as Element;
    if (target.closest('button, input, select, textarea, [role="dialog"], .trading-drawing-overlay')) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    if (adapter.isPriceScaleCoordinate(x)) return;
    const index = adapter.barIndexAtCoordinate(x, allBarsRef.current.length);
    if (index === null) return;
    setReplayPlaying(false);
    restartReplaySession();
    setReplaySelectionIndex(index);
    setReplayStartIndex(index);
    setReplayCursorIndex(index);
  };

  const resetReplay = () => {
    if (replayStartIndex === null) return;
    setReplayPlaying(false);
    restartReplaySession();
    setReplayCursorIndex(replayStartIndex);
  };

  const previousReplayBar = () => {
    if (replayCursorIndex === null || replayStartIndex === null || replayCursorIndex <= replayStartIndex) return;
    setReplayPlaying(false);
    restartReplaySession();
    setReplayCursorIndex(Math.max(replayStartIndex, replayCursorIndex - 1));
  };

  const exitReplay = () => {
    setReplayPlaying(false);
    setReplayMode(false);
  };

  useEffect(() => {
    if (!adapter || !replayMode || !active || replayStartIndex === null) {
      setReplayMarkerX(null);
      return;
    }
    const updateMarker = () => {
      const startBar = allBarsRef.current[replayStartIndex];
      setReplayMarkerX(startBar
        ? adapter.barTimeToCoordinate(startBar.start_time) ?? adapter.timeToCoordinate(startBar.start_time)
        : null);
    };
    const frame = window.requestAnimationFrame(updateMarker);
    window.addEventListener('resize', updateMarker);
    const host = hostRef.current;
    const observer = typeof ResizeObserver === 'undefined' || !host ? null : new ResizeObserver(updateMarker);
    observer?.observe(host as Element);
    const unsubscribeViewport = adapter.onViewportChange(updateMarker);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', updateMarker);
      observer?.disconnect();
      unsubscribeViewport();
    };
  }, [active, adapter, replayCursorIndex, replayMode, replayStartIndex]);

  useEffect(() => {
    const selecting = replayMode && active && replayCursorIndex === null;
    if (!selecting || !adapter || allBarsRef.current.length === 0) {
      setReplaySelectionX(null);
      setReplaySelectionIndex(null);
      return;
    }
    if (replaySelectionIndex === null || replaySelectionIndex >= allBarsRef.current.length) {
      const initialIndex = replayStartIndex ?? adapter.barIndexAtCoordinate(
        adapter.indicatorPlotWidth() / 2,
        allBarsRef.current.length,
      );
      setReplaySelectionIndex(initialIndex);
      return;
    }
    const updateDivider = () => {
      const bar = allBarsRef.current[replaySelectionIndex];
      setReplaySelectionX(bar
        ? adapter.barTimeToCoordinate(bar.start_time) ?? adapter.timeToCoordinate(bar.start_time)
        : null);
    };
    updateDivider();
    window.addEventListener('resize', updateDivider);
    const host = hostRef.current;
    const observer = typeof ResizeObserver === 'undefined' || !host ? null : new ResizeObserver(updateDivider);
    observer?.observe(host as Element);
    const unsubscribeViewport = adapter.onViewportChange(updateDivider);
    return () => {
      window.removeEventListener('resize', updateDivider);
      observer?.disconnect();
      unsubscribeViewport();
    };
  }, [active, adapter, chartQuery.data, replayCursorIndex, replayMode, replaySelectionIndex, replayStartIndex]);

  const replayStartBar = replayStartIndex === null ? null : allBarsRef.current[replayStartIndex] ?? null;
  const replayCurrentBar = replayCursorIndex === null ? null : allBarsRef.current[replayCursorIndex] ?? null;
  const replayHasNextBar = replayCursorIndex !== null && replayCursorIndex < allBarsRef.current.length - 1;

  return (
    <article
      ref={panelRef}
      className={`trading-chart-panel${active ? ' active' : ''}${chartFocusMode ? ' is-chart-focus-mode' : ''}${replayMode && active ? ' replay-active' : ''}`}
      data-chart-id={chartId}
      data-stream-status={streamStatus}
      onPointerDown={onActivate}
      aria-label={`${chartId}${active ? ', active chart' : ''}`}
    >
      <header className="trading-chart-header">
        <div className="trading-chart-heading">
          <div className="trading-chart-title-row">
            <button
              type="button"
              className="trading-chart-symbol-trigger"
              aria-label={`Change symbol for Chart ${chartNumber}`}
              title={`Change symbol for Chart ${chartNumber}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={onOpenSymbolSearch}
            >
              <strong>{chartQuery.data?.instrument.display_symbol ?? instrumentId}</strong>
              <span aria-hidden="true">⌄</span>
            </button>
            <button
              type="button"
              className="trading-compare-trigger"
              aria-label="Compare another symbol"
              title="Compare another symbol"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => setCompareDialogOpen(true)}
            >+</button>
            <span>· {intervalLabel(interval)} · {chartQuery.data?.instrument.venue ?? resolvedBinding?.provider ?? 'Omnix'}</span>
            <i className={`trading-stream-dot ${streamStatus}`} aria-label={`Feed ${streamStatus}`} />
          </div>
          {latest ? (
            <div className="trading-chart-ohlc">
              <span>O <b>{convertedPrice(latest.open, priceScaleMultiplier)}</b></span>
              <span>H <b>{convertedPrice(latest.high, priceScaleMultiplier)}</b></span>
              <span>L <b>{convertedPrice(latest.low, priceScaleMultiplier)}</b></span>
              <span>C <b>{convertedPrice(latest.close, priceScaleMultiplier)}</b></span>
              <span className={direction}>{change >= 0 ? '+' : ''}{convertedPrice(change, priceScaleMultiplier)} ({changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%)</span>
            </div>
          ) : null}
        </div>

        <div
          className="trading-chart-provenance"
          title={`${resolvedBinding?.provider ?? 'Resolving provider'} · ${resolvedBinding?.is_official_api ? 'official API' : 'unofficial API'} · ${provenance?.freshness_mode ?? 'loading'}`}
        >
          <span>{resolvedBinding?.provider ?? 'resolving'}</span>
          <span className={`stream-${streamStatus}`}>{streamStatus}</span>
          <button
            type="button"
            className="trading-chart-fullscreen"
            aria-label={chartFocusMode ? 'Exit chart focus mode' : 'Focus this chart'}
            aria-pressed={chartFocusMode}
            title={chartFocusMode ? 'Show all charts' : 'Focus this chart'}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => void toggleFullscreen()}
          >
            {chartFocusMode ? '↙' : '⛶'}
          </button>
        </div>

        {active ? (
          <div className="trading-drawing-manager" onPointerDown={(event) => event.stopPropagation()}>
            <button type="button" onClick={() => drawings.undo()} aria-label="Undo drawing">↶</button>
            <button type="button" onClick={() => drawings.redo()} aria-label="Redo drawing">↷</button>
            <button type="button" onClick={() => adapterRef.current && downloadDataUrl(adapterRef.current.snapshotDataUrl(), `${chartId}.png`)} aria-label="Snapshot chart">PNG</button>
            {drawings.hasConflict ? (
              <>
                <span role="status">Drawing conflict</span>
                <button type="button" onClick={() => void drawings.resolveConflict('reload')}>Reload server</button>
                <button type="button" onClick={() => void drawings.resolveConflict('overwrite')}>Overwrite server</button>
              </>
            ) : null}
            {selectedDrawing ? (
              <>
                <input aria-label="Drawing color" type="color" value={selectedDrawing.style?.color ?? '#66d9e8'} onChange={(event) => drawings.updateSelected({ style: { ...(selectedDrawing.style ?? { lineWidth: 2, lineStyle: 'solid' }), color: event.target.value } })} />
                <button type="button" aria-pressed={Boolean(selectedDrawing.locked)} onClick={() => drawings.updateSelected({ locked: !selectedDrawing.locked })}>{selectedDrawing.locked ? 'Unlock' : 'Lock'}</button>
                <button type="button" aria-pressed={Boolean(selectedDrawing.hidden)} onClick={() => drawings.updateSelected({ hidden: !selectedDrawing.hidden })}>{selectedDrawing.hidden ? 'Show' : 'Hide'}</button>
                {selectedDrawing.toolType === 'text' ? <input aria-label="Drawing text" type="text" value={selectedDrawing.text ?? ''} onChange={(event) => drawings.updateSelected({ text: event.target.value })} /> : null}
                <button type="button" onClick={() => drawings.removeSelected()} aria-label="Delete selected drawing">×</button>
              </>
            ) : null}
          </div>
        ) : null}
      </header>
      <div
        className={`trading-chart-stage${replayMode && active ? ' is-replay-mode' : ''}`}
        onClickCapture={handleReplayStageClick}
        onContextMenu={handleStageContextMenu}
        onPointerMove={handleStagePointerMove}
        onPointerLeave={handleStagePointerLeave}
      >
        <div ref={hostRef} className={`trading-chart-canvas${drawingTool === 'cursor' && !replayMode ? ' is-pan-ready' : ''}${chartPanning ? ' is-grabbing' : ''}`} data-panning-indicator={panningIndicatorPane ?? undefined} aria-label={`${instrumentId} ${interval} chart`} />
        {adapter ? <TradingIndicatorBackgroundOverlay adapter={adapter} outputs={visibleIndicatorOutputs} /> : null}
        {adapter ? <TradingVolumeProfileOverlay adapter={adapter} outputs={visibleIndicatorOutputs} /> : null}
        {!fullscreenIndicator && !fullscreenMainPane ? paneIndicators.flatMap((indicator) => {
          const geometry = indicatorPaneGeometry.find((item) => item.id === indicator.id);
          if (!geometry || geometry.height <= 40) return [];
          return (['top', 'bottom'] as const).map((edge) => (
            <div
              key={`${indicator.id}-resize-${edge}`}
              className={`trading-indicator-pane-resize-handle ${edge}${resizingIndicatorPane === indicator.id ? ' is-resizing' : ''}`}
              style={{ top: `${edge === 'top' ? geometry.top : geometry.top + geometry.height}px` }}
              data-indicator-id={indicator.id}
              data-edge={edge}
              role="separator"
              aria-orientation="horizontal"
              aria-label={`Resize ${indicator.id.toUpperCase()} ${indicator.period} pane ${edge} border`}
              aria-valuemin={80}
              aria-valuenow={Math.round(geometry.height)}
              onPointerDown={(event) => startIndicatorPaneResize(event, indicator.id, edge)}
            />
          ));
        }) : null}
        {replayMode && active && replayCursorIndex === null && replaySelectionX !== null ? (
          <div
            className="trading-replay-future-overlay"
            style={{ left: `${replaySelectionX}px` }}
            aria-hidden="true"
          />
        ) : null}
        {replayMode && active && replayMarkerX !== null ? (
          <div className="trading-replay-marker" style={{ left: `${replayMarkerX}px` }} aria-hidden="true">
            <span>Replay start</span>
          </div>
        ) : null}
        {replayMode && active && replayCursorIndex === null && replaySelectionX !== null ? (
          <div className="trading-replay-selection-divider" style={{ left: `${replaySelectionX}px` }} aria-hidden="true">
            <span>✂</span>
            <small>{replaySelectionIndex === null ? 'Select replay start' : 'Replay start'}</small>
          </div>
        ) : null}
        {replayMode && active ? (
          <div className="trading-replay-mode-hint" role="status">
            {replayStartBar ? `Replay starts ${new Date(replayStartBar.start_time).toLocaleString()}` : 'Click a candle to choose the replay start'}
          </div>
        ) : null}
        {active && adapter ? (
          <>
            <TradingYAxisControls
              side={priceScaleSettings.side}
              currency={priceScaleCurrency}
              autoScale={priceScaleSettings.autoScale}
              logarithmic={priceScaleSettings.mode === 'logarithmic'}
              visible={priceScaleHovered}
              onCurrencyChange={setPriceScaleCurrency}
              onAutoFit={() => {
                adapter.setPriceScaleAutoScale(true);
                setPriceScaleSettings((current) => ({ ...current, autoScale: true }));
              }}
              onToggleLogarithmic={() => {
                const logarithmic = priceScaleSettings.mode !== 'logarithmic';
                adapter.setPriceScaleMode(logarithmic ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal);
                setPriceScaleSettings((current) => ({ ...current, mode: logarithmic ? 'logarithmic' : 'normal' }));
              }}
            />
            <button
              type="button"
              className="trading-price-scale-trigger"
              aria-label="Open price scale settings"
              aria-expanded={priceScaleMenuOpen}
              title="Price scale settings"
              onPointerDown={(event) => event.stopPropagation()}
              onContextMenu={(event) => event.stopPropagation()}
              onClick={() => setPriceScaleMenuOpen((value) => !value)}
            >
              ⋮
            </button>
            {priceScaleMenuOpen ? (
              <TradingPriceScaleMenu
                adapter={adapter}
                state={priceScaleSettings}
                onChange={(patch) => setPriceScaleSettings((current) => ({ ...current, ...patch }))}
                onClose={() => setPriceScaleMenuOpen(false)}
                onSettings={() => setSettingsVisible(true)}
                rightOffset={rightOffset}
                rightOffsetOptions={rightOffsetOptions}
                onRightOffsetChange={changeRightOffset}
              />
            ) : null}
          </>
        ) : null}
        {legendCount > 0 ? (
          <div
            className={`trading-overlay-indicator-controls trading-indicator-legend${indicatorLegendCollapsed ? ' is-collapsed' : ''}`}
            role="group"
            aria-label="Indicator legend"
            onPointerDown={(event) => event.stopPropagation()}
          >
            {!indicatorLegendCollapsed ? legendIndicators.map((indicator) => {
              const label = `${indicator.id.toUpperCase()} ${indicator.period}`;
              const visible = indicator.visible !== false;
              const docked = indicatorUsesSeparatePane(indicator.id);
              const kind = docked ? 'indicator' : 'overlay';
              return (
                <div key={indicator.id} className={`trading-overlay-indicator${visible ? ' active' : ' hidden'}`}>
                  <span className="trading-overlay-indicator-label">{label}</span>
                  <button
                    type="button"
                    aria-label={`${visible ? 'Hide' : 'Show'} ${label} ${kind}`}
                    aria-pressed={visible}
                    title={`${visible ? 'Hide' : 'Show'} ${label}`}
                    onClick={() => onToggleIndicatorVisibility(indicator.id)}
                  >
                    {visible ? '◉' : '○'}
                  </button>
                  <button
                    type="button"
                    aria-label={`Open ${label} settings`}
                    title={`Open ${label} settings`}
                    onClick={() => setSettingsIndicator(indicator)}
                  >
                    ⚙
                   </button>
                   <button
                     type="button"
                     aria-label={`Open ${label} source code`}
                     title={`Open ${label} source code`}
                     onClick={() => onOpenPineScript(indicator.id)}
                   >
                     {'{}'}
                   </button>
                   <button
                     type="button"
                     className="trading-overlay-indicator-delete"
                    aria-label={`Delete ${label} ${kind}`}
                    title={`Delete ${label}`}
                    onClick={() => onToggleIndicator(indicator.id)}
                  >
                    ×
                  </button>
                </div>
              );
            }) : null}
            {!indicatorLegendCollapsed ? legendComparisons.map((comparison) => (
              <div key={comparison.instrumentId} className={`trading-overlay-indicator${comparison.visible ? ' active' : ' hidden'}`}>
                <span className="trading-overlay-indicator-label">{comparison.label} · {comparisonPercent(comparison.bars)}</span>
                <button
                  type="button"
                  aria-label={`${comparison.visible ? 'Hide' : 'Show'} ${comparison.label}`}
                  aria-pressed={comparison.visible}
                  title={`${comparison.visible ? 'Hide' : 'Show'} ${comparison.label}`}
                  onClick={() => onUpdateComparisons(comparisons.map((item) => item.instrumentId === comparison.instrumentId ? { ...item, visible: !comparison.visible } : item))}
                >{comparison.visible ? '◉' : '○'}</button>
                <button
                  type="button"
                  aria-label={`Open comparison settings for ${comparison.label}`}
                  title="Add or change comparison"
                  onClick={() => setCompareDialogOpen(true)}
                >⚙</button>
                <button
                  type="button"
                  className="trading-overlay-indicator-delete"
                  aria-label={`Remove comparison ${comparison.label}`}
                  title={`Remove ${comparison.label}`}
                  onClick={() => onUpdateComparisons(comparisons.filter((item) => item.instrumentId !== comparison.instrumentId))}
                >×</button>
              </div>
            )) : null}
            <button
              type="button"
              className="trading-indicator-legend-toggle"
              aria-label={indicatorLegendCollapsed ? 'Expand indicator legend' : 'Collapse indicator legend'}
              aria-expanded={!indicatorLegendCollapsed}
              title={indicatorLegendCollapsed ? 'Expand indicator legend' : 'Collapse indicator legend'}
              onClick={() => setIndicatorLegendCollapsed((collapsed) => !collapsed)}
            >
              <span aria-hidden="true">{indicatorLegendCollapsed ? '⌄' : '⌃'}</span>
              {indicatorLegendCollapsed ? <span className="trading-indicator-legend-count">{legendCount}</span> : null}
            </button>
          </div>
        ) : null}
        {paneIndicators.filter((indicator) => !fullscreenMainPane && (!fullscreenIndicator || indicator.id === fullscreenIndicator)).map((indicator, index) => {
          const geometry = indicatorPaneGeometry.find((item) => item.id === indicator.id);
          if (!geometry) return null;
          return (
            <TradingIndicatorPaneControls
              key={indicator.id}
              indicator={indicator}
              geometry={geometry}
              minimized={minimizedIndicators.has(indicator.id)}
              fullscreen={fullscreenIndicator === indicator.id}
              hovered={hoveredIndicatorPane === indicator.id}
              canMoveUp={index > 0}
              canMoveDown={index < paneIndicators.length - 1}
              onToggleMinimized={() => toggleMinimizedIndicator(indicator.id)}
              onToggleFullscreen={() => void toggleFullscreenIndicator(indicator.id)}
              onResetView={() => resetIndicatorPaneView(indicator.id)}
              onSettings={() => setSettingsIndicator(indicator)}
              onSourceCode={() => onOpenPineScript(indicator.id)}
              onMove={(direction) => onMoveIndicator(indicator.id, direction)}
              onClose={() => closeIndicator(indicator.id)}
            />
          );
        })}
        {selectedIndicator && selectedIndicatorConfig ? (
          <TradingIndicatorObjectToolbar
            indicator={selectedIndicatorConfig}
            x={selectedIndicator.x}
            y={selectedIndicator.y}
            docked={indicatorUsesSeparatePane(selectedIndicatorConfig.id)}
            onToggleVisibility={() => onToggleIndicatorVisibility(selectedIndicatorConfig.id)}
            onSettings={() => setSettingsIndicator(selectedIndicatorConfig)}
            onSourceCode={() => onOpenPineScript(selectedIndicatorConfig.id)}
            onResetView={() => resetIndicatorPaneView(selectedIndicatorConfig.id)}
            onRemove={() => {
              setSelectedIndicator(null);
              onToggleIndicator(selectedIndicatorConfig.id);
            }}
            onDismiss={() => setSelectedIndicator(null)}
          />
        ) : null}
        {settingsIndicator ? (
          <TradingIndicatorSettings
            indicator={settingsIndicator}
            onApply={(patch) => onUpdateIndicator(settingsIndicator.id, patch)}
            onClose={() => setSettingsIndicator(null)}
          />
        ) : null}
        <TradingDrawingOverlay
          adapter={adapter}
          instrumentId={instrumentId}
          interval={interval}
          tool={active ? drawingTool : 'cursor'}
          snapMode={drawingSnapMode}
          drawings={drawings.state.drawings}
          selectedId={drawings.state.selectedId}
          onAdd={drawings.add}
          onSelect={(id) => { onActivate(); drawings.select(id); }}
          onMovePoint={drawings.movePoint}
          onTranslateDrawing={drawings.translate}
          onRemove={drawings.remove}
          onToolComplete={() => setDrawingTool('cursor')}
          onAlertAtPoint={active ? (placement, indicatorId) => {
            const indicator = indicatorId
              ? indicators.find((item) => item.id === indicatorId && item.enabled)
              : undefined;
            const supportedIndicatorId = indicatorId && isAlertIndicatorId(indicatorId)
              ? indicatorId
              : undefined;
            setAlertPlacement({
              ...placement,
              ...(supportedIndicatorId ? { indicatorId: supportedIndicatorId } : {}),
              ...(indicator?.period !== undefined ? { indicatorPeriod: indicator.period } : {}),
            });
          } : undefined}
          onContextMenu={active ? openContextMenu : undefined}
        />
        <TradingChartAlertOverlay
          adapter={adapter}
          instrumentId={instrumentId}
          bindingId={provenance?.requested_binding ?? bindingId ?? resolvedBinding?.binding_id ?? null}
          interval={interval}
          latestPrice={latestClose}
          symbol={chartQuery.data?.instrument.display_symbol ?? instrumentId}
          placement={alertPlacement}
          onPlacementConsumed={clearAlertPlacement}
        />
        <TradingPositionOverlay adapter={adapter} accountId={paperAccountId} instrumentId={instrumentId} />
        {tableVisible ? (
          <div className="trading-chart-table-view" role="dialog" aria-label="Chart table view" onPointerDown={(event) => event.stopPropagation()}>
            <header><strong>Table view · {chartQuery.data?.instrument.display_symbol ?? instrumentId}</strong><button type="button" onClick={() => setTableVisible(false)} aria-label="Close table view">×</button></header>
            <table>
              <thead><tr><th>Time</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead>
              <tbody>{bars.slice(-12).reverse().map((bar) => <tr key={bar.start_time}><td>{new Date(bar.start_time).toLocaleString()}</td><td>{convertedPrice(bar.open, priceScaleMultiplier)}</td><td>{convertedPrice(bar.high, priceScaleMultiplier)}</td><td>{convertedPrice(bar.low, priceScaleMultiplier)}</td><td>{convertedPrice(bar.close, priceScaleMultiplier)}</td><td>{price(bar.volume)}</td></tr>)}</tbody>
            </table>
          </div>
        ) : null}
        {objectTreeVisible ? (
          <aside className="trading-chart-object-tree" role="dialog" aria-label="Object tree" onPointerDown={(event) => event.stopPropagation()}>
            <header><strong>Object tree</strong><button type="button" onClick={() => setObjectTreeVisible(false)} aria-label="Close object tree">×</button></header>
            <ul>
              {drawings.state.drawings.map((drawing) => <li key={drawing.drawingId}><span>{drawing.toolType}{drawing.locked ? ' · locked' : ''}</span><button type="button" onClick={() => { drawings.select(drawing.drawingId); setObjectTreeVisible(false); }}>Select</button></li>)}
              {indicators.filter((indicator) => indicator.enabled).map((indicator) => <li key={indicator.id}><span>{indicator.id.toUpperCase()} {indicator.period}</span><button type="button" onClick={() => onToggleIndicator(indicator.id)}>Remove</button></li>)}
              {drawings.state.drawings.length === 0 && indicators.every((indicator) => !indicator.enabled) ? <li><span>No chart objects</span></li> : null}
            </ul>
          </aside>
        ) : null}
        {settingsVisible ? (
          <aside className="trading-chart-settings" role="dialog" aria-label="Chart settings" onPointerDown={(event) => event.stopPropagation()}>
            <header><strong>Chart settings</strong><button type="button" onClick={() => setSettingsVisible(false)} aria-label="Close chart settings">×</button></header>
            <label>Chart type<select value={chartType} onChange={(event) => onChangeChartType(event.target.value as TradingChartType)}>{TRADING_CHART_TYPE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label>Right margin<select aria-label="Chart right margin" value={rightOffset} onChange={(event) => changeRightOffset(event.target.value)}>{rightOffsetOptions.map((offset) => <option key={offset} value={offset}>{offset === 0 ? 'None' : `${offset} bars`}</option>)}</select></label>
            <label>Snap mode<select value={drawingSnapMode} disabled><option>{drawingSnapMode}</option></select></label>
          </aside>
        ) : null}
        {contextMenu ? (
          <>
            <div
              className="trading-chart-context-menu-dismiss-layer"
              aria-hidden="true"
              onPointerDown={() => setContextMenu(null)}
              onContextMenu={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
            />
            <TradingChartContextMenu
              point={contextMenu}
              symbol={contextIndicator
                ? indicatorContextLabel(contextIndicator)
                : contextMenu?.drawingTool === 'trend-line'
                  ? 'trendline'
                  : (chartQuery.data?.instrument.display_symbol ?? instrumentId)}
              indicatorContext={Boolean(contextIndicator)}
              drawingCount={drawings.state.drawings.length}
              indicatorCount={indicators.filter((indicator) => indicator.enabled).length}
              cursorLocked={cursorLocked}
              tableVisible={tableVisible}
              onClose={() => setContextMenu(null)}
              onReset={() => {
                if (contextIndicator) {
                  resetIndicatorPaneView(contextIndicator.id);
                  return;
                }
                selectedRangeRef.current = null;
                adapterRef.current?.fitContent();
                setPriceScaleSettings((current) => ({ ...current, autoScale: true }));
                setSelectedRangeLabel('All');
              }}
              onCopyPrice={copyContextPrice}
              onPastePrice={pasteContextPrice}
              onAddAlert={contextMenu?.indicatorId || !contextMenu?.contextIndicatorId ? contextMenuAlert : null}
              onToggleCursor={() => setCursorLocked((value) => !value)}
              onToggleTable={() => setTableVisible((value) => !value)}
              onObjectTree={() => setObjectTreeVisible(true)}
              onApplyTemplate={applyChartTemplate}
              onRemoveDrawings={() => drawings.removeAll()}
              onRemoveIndicators={onClearIndicators}
              onSettings={() => contextIndicator ? setSettingsIndicator(contextIndicator) : setSettingsVisible(true)}
            />
          </>
        ) : null}
      </div>
      <TradingCompareSymbolDialog
        open={compareDialogOpen}
        currentInstrumentId={instrumentId}
        existingInstrumentIds={comparisons.map((comparison) => comparison.instrumentId)}
        onAdd={(instrument, placement) => {
          if (instrument.instrument_id === instrumentId) return;
          onUpdateComparisons(comparisons.some((comparison) => comparison.instrumentId === instrument.instrument_id)
            ? comparisons.map((comparison) => comparison.instrumentId === instrument.instrument_id ? { ...comparison, placement } : comparison)
            : [...comparisons, { instrumentId: instrument.instrument_id, placement, visible: true }]);
        }}
        onClose={() => setCompareDialogOpen(false)}
      />
      {chartQuery.isLoading ? <div className="trading-chart-state">Loading historical bars…</div> : null}
      {chartQuery.error ? (
        <div className="trading-chart-state error">
          <span>{chartQuery.error.message}</span>
          {chartQuery.error.message.includes('CoinMarketCap API key') && onOpenMarketDataSettings ? (
            <button type="button" onClick={onOpenMarketDataSettings}>Open market-data settings</button>
          ) : null}
        </div>
      ) : null}
      {streamError ? <div className="trading-chart-state error">{streamError}</div> : null}
      {indicatorError ? <div className="trading-chart-state error">Indicator calculation failed: {indicatorError}</div> : null}
      <footer>
        {replayMode && active ? (
          <div className="trading-replay-toolbar" role="group" aria-label="Chart replay controls" onPointerDown={(event) => event.stopPropagation()}>
            <button type="button" onClick={exitReplay} aria-label="Exit replay mode" title="Exit replay mode">×</button>
            <button type="button" onClick={() => setReplayCursorIndex(null)} disabled={replayStartIndex === null} aria-label="Choose replay start" title="Choose replay start">Select bar</button>
            <button type="button" onClick={resetReplay} disabled={replayStartIndex === null} aria-label="Reset replay" title="Reset replay">↤</button>
            <button type="button" onClick={previousReplayBar} disabled={replayCursorIndex === null || replayCursorIndex <= replayStartIndex!} aria-label="Replay previous bar" title="Previous bar">|‹</button>
            <button type="button" className="trading-replay-play" onClick={() => setReplayPlaying((value) => !value)} disabled={replayStartIndex === null || !replayHasNextBar} aria-label={replayPlaying ? 'Pause replay' : 'Play replay'} title={replayPlaying ? 'Pause replay' : 'Play replay'}>{replayPlaying ? 'Ⅱ' : '▶'}</button>
            <button type="button" onClick={() => setReplayCursorIndex((current) => current === null || replayStartIndex === null ? current : Math.min(allBarsRef.current.length - 1, Math.max(replayStartIndex, current + 1)))} disabled={!replayHasNextBar} aria-label="Replay next bar" title="Replay next bar">›|</button>
            <select aria-label="Replay speed" value={replaySpeed} onChange={(event) => setReplaySpeed(event.target.value)}>
              {['0.5', '1', '2', '4', '8'].map((speed) => <option key={speed} value={speed}>{speed}×</option>)}
            </select>
            <span className="trading-replay-progress">{replayCurrentBar ? new Date(replayCurrentBar.end_time).toLocaleDateString() : 'Select a bar'} · {replayCursorIndex === null ? 0 : replayCursorIndex + 1}/{allBarsRef.current.length}</span>
          </div>
        ) : null}
        <nav aria-label={`${chartId} visible range`} onPointerDown={(event) => event.stopPropagation()}>
          {ranges.map((range) => (
            <button
              key={range.label}
              type="button"
              aria-pressed={selectedRangeLabel === range.label}
              aria-label={`${range.label}: ${range.tooltip}`}
              data-tooltip={range.tooltip}
              onClick={() => showRange(range.label, range.days, range.interval)}
            >
              {range.label}
            </button>
          ))}
        </nav>
        <div className="trading-chart-footer-meta">
          <span>{latest?.end_time ? new Date(latest.end_time).toLocaleTimeString() : provenance?.as_of ? new Date(provenance.as_of).toLocaleTimeString() : 'Awaiting data'}</span>
          <span>{streamStatus === 'live' ? 'live source' : provenance?.cached ? 'cached' : 'live source'}</span>
          <span>{drawings.status}</span>
        </div>
      </footer>
    </article>
  );
}
