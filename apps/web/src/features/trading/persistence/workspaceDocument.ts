import type { CoreIndicatorInstance } from '../indicators/coreIndicators';
import {
  MAX_TRADING_CHARTS,
  type TradingChartState,
  type TradingLayout,
  type TradingLinkState,
} from '../tradingStore';

export type TradingWorkspacePayload = {
  schemaVersion: 2;
  name: string;
  layout: TradingLayout;
  activeChartId: string;
  charts: TradingChartState[];
  links: TradingLinkState;
  panels: Record<string, boolean>;
};

type PersistableChart = Omit<TradingChartState, 'indicators' | 'bindingId'> & {
  indicators?: CoreIndicatorInstance[];
  bindingId?: string | null;
};

type LegacyLayout = 'one' | 'two-horizontal' | 'two-vertical' | 'four';

const layouts: TradingLayout[] = ['auto', 'columns-1', 'columns-2', 'columns-3', 'columns-4'];
const legacyLayouts: LegacyLayout[] = ['one', 'two-horizontal', 'two-vertical', 'four'];

export function serializeTradingWorkspace(input: {
  layout: TradingLayout;
  activeChartId: string;
  charts: PersistableChart[];
  links: TradingLinkState;
}): TradingWorkspacePayload {
  return {
    schemaVersion: 2,
    name: 'Main workspace',
    layout: input.layout,
    activeChartId: input.activeChartId,
    charts: input.charts.map((chart) => ({
      ...chart,
      bindingId: chart.bindingId ?? null,
      indicators: (chart.indicators ?? []).map((indicator) => ({ ...indicator })),
    })),
    links: { ...input.links },
    panels: { right: true, bottom: true },
  };
}

function indicator(value: unknown): value is CoreIndicatorInstance {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<CoreIndicatorInstance>;
  const ids = ['sma', 'ema', 'rsi', 'macd', 'bollinger', 'atr', 'vwap'];
  if (!item.id || !ids.includes(item.id)) return false;
  if (typeof item.period !== 'number' || !Number.isInteger(item.period) || item.period < 1) return false;
  if (typeof item.enabled !== 'boolean') return false;
  for (const optionalPeriod of [item.fastPeriod, item.slowPeriod, item.signalPeriod]) {
    if (optionalPeriod !== undefined && (!Number.isInteger(optionalPeriod) || optionalPeriod < 1)) return false;
  }
  if (item.standardDeviations !== undefined && (!Number.isFinite(item.standardDeviations) || item.standardDeviations <= 0)) return false;
  if (item.anchorTime !== undefined && item.anchorTime !== null && typeof item.anchorTime !== 'string') return false;
  return true;
}

function parseCharts(value: unknown): TradingChartState[] | null {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_TRADING_CHARTS) return null;
  const chartTypes = ['candlestick', 'bar', 'line', 'area', 'baseline'];
  const charts: TradingChartState[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') return null;
    const chart = raw as Partial<TradingChartState>;
    if (typeof chart.chartId !== 'string' || typeof chart.instrumentId !== 'string' || typeof chart.interval !== 'string') return null;
    if (!chart.chartType || !chartTypes.includes(chart.chartType)) return null;
    const bindingId = chart.bindingId === undefined || chart.bindingId === null
      ? null
      : typeof chart.bindingId === 'string'
        ? chart.bindingId
        : undefined;
    if (bindingId === undefined) return null;
    const indicators = Array.isArray(chart.indicators) ? chart.indicators.filter(indicator) : [];
    if (Array.isArray(chart.indicators) && indicators.length !== chart.indicators.length) return null;
    charts.push({
      chartId: chart.chartId,
      instrumentId: chart.instrumentId,
      bindingId,
      interval: chart.interval,
      chartType: chart.chartType,
      indicators,
    });
  }
  if (new Set(charts.map((chart) => chart.chartId)).size !== charts.length) return null;
  return charts;
}

function parseLinks(value: unknown): TradingLinkState | null {
  if (!value || typeof value !== 'object') return null;
  const links = value as Partial<TradingLinkState>;
  if (['instrument', 'interval', 'crosshair', 'visibleRange'].some((key) => typeof links[key as keyof TradingLinkState] !== 'boolean')) return null;
  return links as TradingLinkState;
}

function migrateLegacyCharts(
  charts: TradingChartState[],
  layout: LegacyLayout,
  activeChartId: string,
): TradingChartState[] {
  const activeIndex = Math.max(0, charts.findIndex((chart) => chart.chartId === activeChartId));
  if (layout === 'one') return charts.slice(activeIndex, activeIndex + 1).length === 1
    ? charts.slice(activeIndex, activeIndex + 1)
    : charts.slice(0, 1);
  if (layout === 'four') return charts.slice(0, 4);
  const selected = charts.slice(activeIndex, activeIndex + 2);
  return selected.length === 2 ? selected : charts.slice(0, 2);
}

function migrateLegacyLayout(layout: LegacyLayout): TradingLayout {
  if (layout === 'one' || layout === 'two-vertical') return 'columns-1';
  return 'columns-2';
}

export function parseTradingWorkspace(value: unknown): TradingWorkspacePayload | null {
  if (!value || typeof value !== 'object') return null;
  const payload = value as Record<string, unknown>;
  const charts = parseCharts(payload.charts);
  const links = parseLinks(payload.links);
  if (!charts || !links) return null;

  if (payload.schemaVersion === 1) {
    if (typeof payload.layout !== 'string' || !legacyLayouts.includes(payload.layout as LegacyLayout)) return null;
    const legacyLayout = payload.layout as LegacyLayout;
    const requestedActive = typeof payload.activeChartId === 'string' ? payload.activeChartId : charts[0].chartId;
    const visibleCharts = migrateLegacyCharts(charts, legacyLayout, requestedActive);
    const activeChartId = visibleCharts.some((chart) => chart.chartId === requestedActive)
      ? requestedActive
      : visibleCharts[0].chartId;
    return {
      schemaVersion: 2,
      name: typeof payload.name === 'string' ? payload.name : 'Main workspace',
      layout: migrateLegacyLayout(legacyLayout),
      activeChartId,
      charts: visibleCharts,
      links,
      panels: payload.panels && typeof payload.panels === 'object' ? payload.panels as Record<string, boolean> : {},
    };
  }

  if (payload.schemaVersion !== 2 || typeof payload.layout !== 'string' || !layouts.includes(payload.layout as TradingLayout)) return null;
  const requestedActive = typeof payload.activeChartId === 'string' ? payload.activeChartId : charts[0].chartId;
  return {
    schemaVersion: 2,
    name: typeof payload.name === 'string' ? payload.name : 'Main workspace',
    layout: payload.layout as TradingLayout,
    activeChartId: charts.some((chart) => chart.chartId === requestedActive) ? requestedActive : charts[0].chartId,
    charts,
    links,
    panels: payload.panels && typeof payload.panels === 'object' ? payload.panels as Record<string, boolean> : {},
  };
}
