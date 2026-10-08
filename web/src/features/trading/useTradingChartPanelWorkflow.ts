import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { chartPalette } from './chartPalette';
import { tradingApi } from './tradingApi';
import {
  barCountdownEnabled,
  centeredLogicalRange,
  chartTemplatePayload,
  chartTemplateRecordId,
  copyImageDataUrlToClipboard,
  dataDelayLabel,
  extendedSessionPriceLine,
  hasExtendedHoursBars,
  marketStatusLabel,
  paneDoubleClickAction,
  parseChartTemplate,
  parseGoToDate,
  planGoToDate,
  type ChartTemplate,
} from './tradingChartWorkflow';
import { isTradingFormulaInstrumentId } from './tradingFormula';
import { tradingIntervalDurationMs } from './tradingIntervals';
import { useTradingStore, type TradingChartSettings } from './tradingStore';
import { dateInputValue } from './tradingTime';
import type { MarketBar } from './tradingTypes';
import type { TradingChartPanelProps } from './tradingChartPanelModel';
import type { useChartPanelState } from './useTradingChartPanelState';
import type { useChartIndicatorScheduling, useChartPanelData } from './useTradingChartPanelData';
import type { useChartLifecycle } from './useTradingChartPanelLifecycle';
import type { useChartSync } from './useTradingChartPanelSync';
import type { useChartView } from './useTradingChartPanelView';
import type { useChartIndicatorActions, useChartRangeActions } from './useTradingChartPanelActions';
import type { useChartReplayActions } from './useTradingChartPanelReplay';

type WorkflowInput = TradingChartPanelProps
  & ReturnType<typeof useChartPanelState>
  & ReturnType<typeof useChartIndicatorScheduling>
  & ReturnType<typeof useChartPanelData>
  & ReturnType<typeof useChartLifecycle>
  & ReturnType<typeof useChartSync>
  & ReturnType<typeof useChartView>
  & ReturnType<typeof useChartIndicatorActions>
  & ReturnType<typeof useChartRangeActions>
  & ReturnType<typeof useChartReplayActions>;

export type GoToDateTarget = string | number | Date;
export type GoToDateResult = 'scrolled' | 'loading' | 'invalid' | 'unavailable';
export type ChartImageCopyStatus = 'idle' | 'copying' | 'copied' | 'error';

type PendingGoToDate = { targetMs: number; key: string; firstBarMs: number | null };

const firstBarTime = (bars: readonly MarketBar[]) => {
  const value = Date.parse(bars[0]?.start_time ?? '');
  return Number.isFinite(value) ? value : null;
};

/** Go to date: scroll to the bar holding a time, loading older history on the existing bars request first. */
function useChartGoToDate(ws: WorkflowInput) {
  const {
    adapterRef, allBarsRef, chartQuery, historyLimit, instrumentId, interval, loadedBars, replayMode,
    selectedRangeRef, selectedTimezone, setHistoryLimitOverride, setSelectedRangeLabel,
  } = ws;
  const [goToDateOpen, setGoToDateOpen] = useState(false);
  const [goToDateError, setGoToDateError] = useState<string | null>(null);
  const [goToDateLoading, setGoToDateLoading] = useState(false);
  const pendingGoToRef = useRef<PendingGoToDate | null>(null);
  const historyKey = `${instrumentId}|${interval}`;

  const finish = useCallback((error: string | null) => {
    pendingGoToRef.current = null;
    setGoToDateLoading(false);
    setGoToDateError(error);
  }, []);

  const runGoToDate = useCallback((pending: PendingGoToDate): GoToDateResult => {
    const bars = allBarsRef.current;
    const plan = planGoToDate(bars, pending.targetMs, historyLimit);
    if (plan.kind === 'scroll') {
      finish(null);
      const targetAdapter = adapterRef.current;
      if (targetAdapter) {
        const timeScale = targetAdapter.api().timeScale();
        selectedRangeRef.current = null;
        setSelectedRangeLabel('');
        timeScale.setVisibleLogicalRange(centeredLogicalRange(plan.index, timeScale.getVisibleLogicalRange()));
      }
      setGoToDateOpen(false);
      return 'scrolled';
    }
    const firstBarMs = firstBarTime(bars);
    const noProgress = pending.firstBarMs !== null && firstBarMs !== null && firstBarMs >= pending.firstBarMs;
    if (plan.kind === 'unavailable' || noProgress) {
      const earliest = bars[0]?.start_time;
      finish(earliest
        ? `No earlier history is available; the chart starts ${dateInputValue(earliest, selectedTimezone)}.`
        : 'No chart history is loaded.');
      return 'unavailable';
    }
    pendingGoToRef.current = { ...pending, firstBarMs };
    setGoToDateLoading(true);
    setGoToDateError(null);
    setHistoryLimitOverride({ key: pending.key, limit: plan.limit });
    return 'loading';
  }, [adapterRef, allBarsRef, finish, historyLimit, selectedRangeRef, selectedTimezone, setHistoryLimitOverride, setSelectedRangeLabel]);

  /** Scrolls the chart to the bar holding a time, loading older history first when needed. Strings are dates in the chart timezone. */
  const goToDate = useCallback((target: GoToDateTarget): GoToDateResult => {
    if (replayMode) {
      setGoToDateError('Leave replay to go to a date.');
      return 'invalid';
    }
    const targetMs = typeof target === 'string'
      ? parseGoToDate(target, selectedTimezone)
      : target instanceof Date ? target.getTime() : target;
    if (targetMs === null || !Number.isFinite(targetMs)) {
      setGoToDateError('Choose a date.');
      return 'invalid';
    }
    return runGoToDate({ targetMs, key: historyKey, firstBarMs: null });
  }, [historyKey, replayMode, runGoToDate, selectedTimezone]);

  // Each history load re-runs a pending request: scroll if the bar arrived, or ask for more.
  useEffect(() => {
    const pending = pendingGoToRef.current;
    if (!pending || chartQuery.isFetching) return;
    if (pending.key !== historyKey) {
      finish(null);
      return;
    }
    runGoToDate(pending);
  }, [chartQuery.isFetching, finish, historyKey, loadedBars, runGoToDate]);

  /** The default date for the go-to-date box: the bar in the middle of the view. */
  const goToDateDefault = () => {
    const bars = allBarsRef.current;
    const range = adapterRef.current?.api().timeScale().getVisibleLogicalRange();
    const index = range ? Math.round((range.from + range.to) / 2) : bars.length - 1;
    const bar = bars[Math.max(0, Math.min(bars.length - 1, index))];
    return dateInputValue(bar ? bar.start_time : Date.now(), selectedTimezone);
  };

  /** Opens the go-to-date box; the keyboard layer's `chart.goToDate` command calls this. */
  const openGoToDate = useCallback(() => {
    setGoToDateError(null);
    setGoToDateOpen(true);
  }, []);

  return { goToDateOpen, setGoToDateOpen, goToDateError, goToDateLoading, goToDate, openGoToDate, goToDateDefault };
}

/** Copy chart image. Omnix stores no snapshots server-side, so there is no snapshot link to copy. */
function useChartImageCopy(adapterRef: WorkflowInput['adapterRef']) {
  const [chartImageCopyStatus, setChartImageCopyStatus] = useState<ChartImageCopyStatus>('idle');
  const copyStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (copyStatusTimerRef.current) clearTimeout(copyStatusTimerRef.current);
  }, []);

  /** Copies a PNG of the chart to the clipboard; resolves to whether it was copied. */
  const copyChartImage = useCallback(async (): Promise<boolean> => {
    const targetAdapter = adapterRef.current;
    if (!targetAdapter) return false;
    setChartImageCopyStatus('copying');
    const copied = await copyImageDataUrlToClipboard(targetAdapter.snapshotDataUrl()).then(() => true, () => false);
    setChartImageCopyStatus(copied ? 'copied' : 'error');
    if (copyStatusTimerRef.current) clearTimeout(copyStatusTimerRef.current);
    copyStatusTimerRef.current = setTimeout(() => setChartImageCopyStatus('idle'), 2_000);
    return copied;
  }, [adapterRef]);

  return { chartImageCopyStatus, copyChartImage };
}

/** Chart templates: a chart's style and indicators, saved with the indicator-preset documents. */
function useChartTemplates(ws: WorkflowInput) {
  const { chartId, chartSettings, chartType, indicators } = ws;
  const updateChart = useTradingStore((state) => state.updateChart);
  const setIndicators = useTradingStore((state) => state.setIndicators);
  const { data: templateRecords, refetch: refetchTemplates } = useQuery({
    queryKey: ['trading', 'indicator-presets'],
    queryFn: () => tradingApi.documents('indicator-presets'),
    enabled: false,
    staleTime: 30_000,
  });
  const chartTemplates: ChartTemplate[] = (templateRecords ?? []).flatMap((record) => {
    const template = parseChartTemplate(record);
    return template ? [template] : [];
  });
  const [chartTemplateStatus, setChartTemplateStatus] = useState<'idle' | 'saving' | 'error'>('idle');

  const loadChartTemplates = useCallback(() => { void refetchTemplates(); }, [refetchTemplates]);

  /** Saves this chart's style and indicators, without its symbol or interval, as a template. */
  const saveChartTemplate = useCallback(async (name: string): Promise<boolean> => {
    setChartTemplateStatus('saving');
    try {
      const payload = chartTemplatePayload({ name, chartType, settings: chartSettings, indicators });
      await tradingApi.createDocument('indicator-presets', chartTemplateRecordId(name), payload);
      setChartTemplateStatus('idle');
      void refetchTemplates();
      return true;
    } catch {
      setChartTemplateStatus('error');
      return false;
    }
  }, [chartSettings, chartType, indicators, refetchTemplates]);

  /** Applies a template's chart type, settings and indicators; the symbol and interval stay. */
  const applyChartTemplateRecord = useCallback((template: ChartTemplate) => {
    updateChart(chartId, { chartType: template.chartType, settings: { ...template.settings } });
    setIndicators(chartId, template.indicators);
  }, [chartId, setIndicators, updateChart]);

  const deleteChartTemplate = useCallback(async (template: ChartTemplate) => {
    const record = templateRecords?.find((item) => item.record_id === template.recordId);
    if (!record) return;
    try {
      await tradingApi.archiveDocument('indicator-presets', record);
      void refetchTemplates();
    } catch {
      setChartTemplateStatus('error');
    }
  }, [refetchTemplates, templateRecords]);

  return { chartTemplates, chartTemplateStatus, loadChartTemplates, saveChartTemplate, applyChartTemplateRecord, deleteChartTemplate };
}

/** Market session (from the server's exchange calendar) and data delay for the legend. */
function useChartMarketStatus(ws: WorkflowInput) {
  const { instrumentId, provenance, resolvedBinding } = ws;
  const { data } = useQuery({
    queryKey: ['trading', 'market-status', instrumentId],
    queryFn: () => tradingApi.marketStatus(instrumentId),
    enabled: Boolean(instrumentId) && !isTradingFormulaInstrumentId(instrumentId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: 1,
  });
  return {
    marketStatus: data ? marketStatusLabel(data.status, data.always_open) : null,
    marketStatusValue: data?.status ?? null,
    dataDelay: dataDelayLabel(resolvedBinding, provenance),
  };
}

/**
 * The chart workflow items of TVP-2.5 for one chart panel: chart settings, the pre/post-market
 * price line, go to date (with history loading), copy chart image, pane maximise/collapse by
 * double-click, chart templates, and market status / data delay for the legend.
 *
 * Keyboard commands (TVP-2.1–2.4) call `openGoToDate`, `goToDate` and `copyChartImage` from this
 * hook's results; it binds no keys itself.
 */
export function useChartWorkflow(ws: WorkflowInput) {
  const {
    active, adapter, adapterRef, chartFocusMode, chartId, chartQuery, chartSettings, drawingTool,
    fullscreenIndicator, fullscreenMainPane, hostRef, interval, paneIndicators, replayMode, showExtendedHours,
    toggleFullscreen, toggleFullscreenIndicator, toggleMinimizedIndicator,
  } = ws;
  const updateChart = useTradingStore((state) => state.updateChart);
  const settings: TradingChartSettings = chartSettings ?? {};

  const updateChartSettings = useCallback((patch: Partial<TradingChartSettings>) => {
    const current = useTradingStore.getState().charts.find((chart) => chart.chartId === chartId)?.settings ?? {};
    updateChart(chartId, { settings: { ...current, ...patch } });
  }, [chartId, updateChart]);

  const rawBars = (chartQuery.data?.bars ?? []) as MarketBar[];
  const barCountdownOn = barCountdownEnabled(settings, interval);

  // The pre/post-market price line follows the newest bar, whether or not extended bars are shown.
  const extendedPriceLineEnabled = settings.extendedPriceLine !== false && !replayMode;
  const extendedLine = extendedPriceLineEnabled ? extendedSessionPriceLine(rawBars) : null;
  const extendedLinePrice = extendedLine?.price ?? null;
  const extendedLineSession = extendedLine?.session ?? null;
  useEffect(() => {
    if (!adapter) return;
    adapter.setSessionPriceLine(extendedLinePrice === null || extendedLineSession === null ? null : {
      price: extendedLinePrice,
      title: extendedLineSession === 'pre' ? 'Pre-market' : 'Post-market',
      color: extendedLineSession === 'pre' ? chartPalette.cyan : chartPalette.amber,
    });
  }, [adapter, extendedLinePrice, extendedLineSession]);

  /** Double-click maximises the pane under the pointer; Ctrl/Cmd + double-click collapses an indicator pane. */
  const handleStageDoubleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const targetAdapter = adapterRef.current;
    const host = hostRef.current;
    if (!targetAdapter || !host || drawingTool !== 'cursor' || (replayMode && active)) return;
    if (!host.contains(event.target as Node)) return;
    // Double-clicking a price scale resets it (lightweight-charts); leave that alone.
    if (targetAdapter.isPriceScaleCoordinate(event.clientX - host.getBoundingClientRect().left)) return;
    const action = paneDoubleClickAction(
      targetAdapter.paneAtClientY(event.clientY),
      event.ctrlKey || event.metaKey,
      { indicatorPaneCount: paneIndicators.length, mainPaneFullscreen: fullscreenMainPane && chartFocusMode, fullscreenIndicator },
    );
    if (!action) return;
    event.preventDefault();
    if (action.type === 'toggle-indicator-fullscreen') toggleFullscreenIndicator(action.id);
    else if (action.type === 'toggle-indicator-minimized') toggleMinimizedIndicator(action.id);
    else toggleFullscreen();
  };

  return {
    updateChartSettings,
    extendedHoursAvailable: hasExtendedHoursBars(rawBars),
    showExtendedHours,
    barCountdownOn,
    barCountdownVisible: barCountdownOn && !replayMode,
    barCountdownAvailable: tradingIntervalDurationMs(interval) !== null,
    extendedPriceLineEnabled,
    handleStageDoubleClick,
    ...useChartGoToDate(ws),
    ...useChartImageCopy(adapterRef),
    ...useChartTemplates(ws),
    ...useChartMarketStatus(ws),
  };
}
