import type { CoreIndicatorInstance } from '../indicators/coreIndicators';
import type { TradingChartState, TradingLayout, TradingLinkState } from '../tradingStore';

export type TradingWorkspacePayload = {
  schemaVersion: 1;
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

export function serializeTradingWorkspace(input: {
  layout: TradingLayout;
  activeChartId: string;
  charts: PersistableChart[];
  links: TradingLinkState;
}): TradingWorkspacePayload {
  return {
    schemaVersion: 1,
    name: 'Main workspace',
    layout: input.layout,
    activeChartId: input.activeChartId,
    charts: input.charts.map((chart) => ({
      ...chart,
      bindingId: chart.bindingId ?? null,
      indicators: (chart.indicators ?? []).map((indicator) => ({ ...indicator })),
    })),
    links: { ...input.links },
    panels: { right: true, bottom: false },
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

export function parseTradingWorkspace(value: unknown): TradingWorkspacePayload | null {
  if (!value || typeof value !== 'object') return null;
  const payload = value as Partial<TradingWorkspacePayload>;
  const layouts: TradingLayout[] = ['one', 'two-horizontal', 'two-vertical', 'four'];
  if (payload.schemaVersion !== 1 || !payload.layout || !layouts.includes(payload.layout)) return null;
  if (!Array.isArray(payload.charts) || payload.charts.length < 1) return null;
  if (!payload.links || typeof payload.links !== 'object') return null;
  const charts: TradingChartState[] = [];
  const chartTypes = ['candlestick', 'bar', 'line', 'area', 'baseline'];
  for (const raw of payload.charts) {
    if (!raw || typeof raw.chartId !== 'string' || typeof raw.instrumentId !== 'string' || typeof raw.interval !== 'string') return null;
    if (!chartTypes.includes(raw.chartType)) return null;
    const bindingId = raw.bindingId === undefined || raw.bindingId === null
      ? null
      : typeof raw.bindingId === 'string'
        ? raw.bindingId
        : undefined;
    if (bindingId === undefined) return null;
    const indicators = Array.isArray(raw.indicators) ? raw.indicators.filter(indicator) : [];
    if (Array.isArray(raw.indicators) && indicators.length !== raw.indicators.length) return null;
    charts.push({ ...raw, chartType: raw.chartType, bindingId, indicators } as TradingChartState);
  }
  const links = payload.links as Partial<TradingLinkState>;
  if (['instrument', 'interval', 'crosshair', 'visibleRange'].some((key) => typeof links[key as keyof TradingLinkState] !== 'boolean')) return null;
  return {
    schemaVersion: 1,
    name: typeof payload.name === 'string' ? payload.name : 'Main workspace',
    layout: payload.layout,
    activeChartId: typeof payload.activeChartId === 'string' ? payload.activeChartId : charts[0].chartId,
    charts,
    links: links as TradingLinkState,
    panels: payload.panels && typeof payload.panels === 'object' ? payload.panels : {},
  };
}
