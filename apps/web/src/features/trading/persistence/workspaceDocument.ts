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

export function serializeTradingWorkspace(input: {
  layout: TradingLayout;
  activeChartId: string;
  charts: TradingChartState[];
  links: TradingLinkState;
}): TradingWorkspacePayload {
  return {
    schemaVersion: 1,
    name: 'Main workspace',
    layout: input.layout,
    activeChartId: input.activeChartId,
    charts: input.charts.map((chart) => ({ ...chart })),
    links: { ...input.links },
    panels: { right: true, bottom: false },
  };
}

export function parseTradingWorkspace(value: unknown): TradingWorkspacePayload | null {
  if (!value || typeof value !== 'object') return null;
  const payload = value as Partial<TradingWorkspacePayload>;
  if (payload.schemaVersion !== 1 || (payload.layout !== 'one' && payload.layout !== 'four')) return null;
  if (!Array.isArray(payload.charts) || payload.charts.length < 1) return null;
  if (!payload.links || typeof payload.links !== 'object') return null;
  const charts = payload.charts.filter((chart): chart is TradingChartState => (
    Boolean(chart)
    && typeof chart.chartId === 'string'
    && typeof chart.instrumentId === 'string'
    && typeof chart.interval === 'string'
    && (chart.chartType === 'candlestick' || chart.chartType === 'line')
  ));
  if (charts.length !== payload.charts.length) return null;
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
