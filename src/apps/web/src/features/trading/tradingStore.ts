import { create } from 'zustand';
import type { TradingChartType } from './chart/chartAdapter';
import type { DrawingSnapMode, DrawingTool } from './drawings/drawingCommands';
import { indicatorUsesSeparatePane, type CoreIndicatorId, type CoreIndicatorInstance } from './indicators/coreIndicators';

export type TradingLayout = 'auto' | 'columns-1' | 'columns-2' | 'columns-3' | 'columns-4';
export const MIN_TRADING_CHARTS = 1;
export const MAX_TRADING_CHARTS = 16;

export type TradingChartState = {
  chartId: string;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  chartType: TradingChartType;
  indicators: CoreIndicatorInstance[];
};
export type TradingIndicatorMove = 'up' | 'down';
export type TradingLinkState = {
  instrument: boolean;
  interval: boolean;
  crosshair: boolean;
  visibleRange: boolean;
};
export type TradingPanelState = {
  right: boolean;
  bottom: boolean;
};

type TradingWorkspaceState = {
  layout: TradingLayout;
  activeChartId: string;
  replayMode: boolean;
  drawingTool: DrawingTool;
  drawingSnapMode: DrawingSnapMode;
  charts: TradingChartState[];
  links: TradingLinkState;
  panels: TradingPanelState;
  favoriteInstrumentIds: string[];
  setLayout: (layout: TradingLayout) => void;
  setActiveChart: (chartId: string) => void;
  setReplayMode: (enabled: boolean) => void;
  addChart: () => void;
  removeChart: (chartId?: string) => void;
  setChartCount: (count: number) => void;
  setDrawingTool: (tool: DrawingTool) => void;
  setDrawingSnapMode: (mode: DrawingSnapMode) => void;
  updateChart: (chartId: string, patch: Partial<Omit<TradingChartState, 'chartId'>>) => void;
  toggleIndicator: (chartId: string, id: CoreIndicatorId, period?: number) => void;
  toggleIndicatorVisibility: (chartId: string, id: CoreIndicatorId) => void;
  moveIndicator: (chartId: string, id: CoreIndicatorId, direction: TradingIndicatorMove) => void;
  setIndicators: (chartId: string, indicators: CoreIndicatorInstance[]) => void;
  setLink: (key: keyof TradingLinkState, enabled: boolean) => void;
  setPanel: (key: keyof TradingPanelState, open: boolean) => void;
  toggleFavoriteInstrument: (instrumentId: string) => void;
};

const defaultInstrument = 'crypto:BINANCE:spot:BTC-USDT';
export const defaultTradingIndicators = (): CoreIndicatorInstance[] => [
  { id: 'sma', period: 20, enabled: true },
  { id: 'ema', period: 20, enabled: false },
  { id: 'rsi', period: 14, enabled: true },
  { id: 'macd', period: 9, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9, enabled: false },
  { id: 'bollinger', period: 20, standardDeviations: 2, enabled: false },
  { id: 'atr', period: 14, enabled: false },
  { id: 'vwap', period: 1, anchorTime: null, enabled: false },
];

function initialChart(): TradingChartState {
  return {
    chartId: 'chart-1',
    instrumentId: defaultInstrument,
    bindingId: null,
    interval: '1h',
    chartType: 'candlestick',
    indicators: defaultTradingIndicators(),
  };
}

function nextChartId(charts: readonly TradingChartState[]): string {
  let index = 1;
  const ids = new Set(charts.map((chart) => chart.chartId));
  while (ids.has(`chart-${index}`)) index += 1;
  return `chart-${index}`;
}

function copyChart(source: TradingChartState, chartId: string): TradingChartState {
  return {
    ...source,
    chartId,
    indicators: source.indicators.map((indicator) => ({ ...indicator })),
  };
}

function boundedChartCount(count: number): number {
  if (!Number.isFinite(count)) return MIN_TRADING_CHARTS;
  return Math.max(MIN_TRADING_CHARTS, Math.min(MAX_TRADING_CHARTS, Math.trunc(count)));
}

export const useTradingStore = create<TradingWorkspaceState>((set) => ({
  layout: 'auto',
  activeChartId: 'chart-1',
  replayMode: false,
  drawingTool: 'cursor',
  drawingSnapMode: 'ohlc',
  charts: [initialChart()],
  links: { instrument: false, interval: false, crosshair: true, visibleRange: true },
  panels: { right: true, bottom: true },
  favoriteInstrumentIds: [],
  setLayout: (layout) => set({ layout }),
  setActiveChart: (activeChartId) => set((state) => (
    state.charts.some((chart) => chart.chartId === activeChartId) ? { activeChartId } : state
  )),
  setReplayMode: (replayMode) => set({ replayMode }),
  addChart: () => set((state) => {
    if (state.charts.length >= MAX_TRADING_CHARTS) return state;
    const source = state.charts.find((chart) => chart.chartId === state.activeChartId) ?? state.charts[0] ?? initialChart();
    const chart = copyChart(source, nextChartId(state.charts));
    return { charts: [...state.charts, chart], activeChartId: chart.chartId };
  }),
  removeChart: (chartId) => set((state) => {
    if (state.charts.length <= MIN_TRADING_CHARTS) return state;
    const targetId = chartId ?? state.activeChartId;
    const targetIndex = state.charts.findIndex((chart) => chart.chartId === targetId);
    if (targetIndex < 0) return state;
    const charts = state.charts.filter((chart) => chart.chartId !== targetId);
    const activeChartId = state.activeChartId === targetId
      ? charts[Math.min(targetIndex, charts.length - 1)].chartId
      : state.activeChartId;
    return { charts, activeChartId };
  }),
  setChartCount: (count) => set((state) => {
    const target = boundedChartCount(count);
    if (target === state.charts.length) return state;
    if (target < state.charts.length) {
      const charts = state.charts.slice(0, target);
      return {
        charts,
        activeChartId: charts.some((chart) => chart.chartId === state.activeChartId)
          ? state.activeChartId
          : charts[charts.length - 1].chartId,
      };
    }
    const charts = [...state.charts];
    const source = state.charts.find((chart) => chart.chartId === state.activeChartId) ?? state.charts[0] ?? initialChart();
    while (charts.length < target) {
      charts.push(copyChart(source, nextChartId(charts)));
    }
    return { charts };
  }),
  setDrawingTool: (drawingTool) => set({ drawingTool }),
  setDrawingSnapMode: (drawingSnapMode) => set({ drawingSnapMode }),
  updateChart: (chartId, patch) => set((state) => {
    const instrumentChanged = patch.instrumentId !== undefined;
    const linkedInstrument = instrumentChanged && state.links.instrument;
    const linkedInterval = patch.interval !== undefined && state.links.interval;
    return {
      charts: state.charts.map((chart) => {
        if (chart.chartId === chartId) {
          return {
            ...chart,
            ...patch,
            ...(instrumentChanged && patch.bindingId === undefined ? { bindingId: null } : {}),
          };
        }
        return {
          ...chart,
          ...(linkedInstrument ? { instrumentId: patch.instrumentId, bindingId: null } : {}),
          ...(linkedInterval ? { interval: patch.interval } : {}),
        };
      }),
    };
  }),
  toggleIndicator: (chartId, id, period) => set((state) => ({
    charts: state.charts.map((chart) => chart.chartId !== chartId ? chart : {
      ...chart,
      indicators: chart.indicators.map((indicator) => indicator.id !== id ? indicator : {
        ...indicator,
        enabled: !indicator.enabled,
        visible: indicator.enabled ? false : true,
        period: period ?? indicator.period,
      }),
    }),
  })),
  toggleIndicatorVisibility: (chartId, id) => set((state) => ({
    charts: state.charts.map((chart) => chart.chartId !== chartId ? chart : {
      ...chart,
      indicators: chart.indicators.map((indicator) => indicator.id !== id || !indicator.enabled ? indicator : {
        ...indicator,
        visible: indicator.visible === false,
      }),
    }),
  })),
  moveIndicator: (chartId, id, direction) => set((state) => ({
    charts: state.charts.map((chart) => {
      if (chart.chartId !== chartId || !indicatorUsesSeparatePane(id)) return chart;
      const paneIndicators = chart.indicators.filter((indicator) => indicatorUsesSeparatePane(indicator.id) && indicator.enabled);
      const currentIndex = paneIndicators.findIndex((indicator) => indicator.id === id);
      if (currentIndex < 0) return chart;
      const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
      if (targetIndex < 0 || targetIndex >= paneIndicators.length) return chart;
      const nextPaneIndicators = [...paneIndicators];
      [nextPaneIndicators[currentIndex], nextPaneIndicators[targetIndex]] = [nextPaneIndicators[targetIndex], nextPaneIndicators[currentIndex]];
      let paneIndex = 0;
      const indicators = chart.indicators.map((indicator) => {
        if (!indicatorUsesSeparatePane(indicator.id) || !indicator.enabled) return indicator;
        const next = nextPaneIndicators[paneIndex];
        paneIndex += 1;
        return next ?? indicator;
      });
      return { ...chart, indicators };
    }),
  })),
  setIndicators: (chartId, indicators) => set((state) => ({
    charts: state.charts.map((chart) => chart.chartId === chartId
      ? { ...chart, indicators: indicators.map((indicator) => ({ ...indicator })) }
      : chart),
  })),
  setLink: (key, enabled) => set((state) => ({ links: { ...state.links, [key]: enabled } })),
  setPanel: (key, open) => set((state) => ({ panels: { ...state.panels, [key]: open } })),
  toggleFavoriteInstrument: (instrumentId) => set((state) => ({
    favoriteInstrumentIds: state.favoriteInstrumentIds.includes(instrumentId)
      ? state.favoriteInstrumentIds.filter((item) => item !== instrumentId)
      : [...state.favoriteInstrumentIds, instrumentId],
  })),
}));
