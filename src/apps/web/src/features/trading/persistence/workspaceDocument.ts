import type { CoreIndicatorInstance, CoreIndicatorStyle } from '../indicators/coreIndicators';
import { TRADING_CHART_TYPE_OPTIONS } from '../chart/chartAdapter';
import { binanceInstrumentIdFor } from '../cryptoInstrumentDefaults';
import {
  MAX_TRADING_CHARTS,
  type TradingChartState,
  type TradingLayout,
  type TradingLinkState,
  type TradingPanelState,
} from '../tradingStore';

export type TradingWorkspacePayload = {
  schemaVersion: 3;
  name: string;
  layout: TradingLayout;
  activeChartId: string;
  charts: TradingChartState[];
  links: TradingLinkState;
  panels: TradingPanelState;
  favoriteInstrumentIds: string[];
};

type PersistableChart = Omit<TradingChartState, 'indicators' | 'bindingId'> & {
  indicators?: CoreIndicatorInstance[];
  bindingId?: string | null;
};

type LegacyLayout = 'one' | 'two-horizontal' | 'two-vertical' | 'four';

const layouts: TradingLayout[] = ['auto', 'columns-1', 'columns-2', 'columns-3', 'columns-4'];
const legacyLayouts: LegacyLayout[] = ['one', 'two-horizontal', 'two-vertical', 'four'];

export function serializeTradingWorkspace(input: {
  name?: string;
  layout: TradingLayout;
  activeChartId: string;
  charts: PersistableChart[];
  links: TradingLinkState;
  panels?: TradingPanelState;
  favoriteInstrumentIds?: string[];
}): TradingWorkspacePayload {
  return {
    schemaVersion: 3,
    name: input.name?.trim() || 'Main Workspace',
    layout: input.layout,
    activeChartId: input.activeChartId,
    charts: input.charts.map((chart) => ({
      ...chart,
      bindingId: chart.bindingId ?? null,
      indicators: (chart.indicators ?? []).map((indicator) => ({ ...indicator })),
    })),
    links: { ...input.links },
    panels: { ...(input.panels ?? { right: true, bottom: true }) },
    favoriteInstrumentIds: [...new Set(input.favoriteInstrumentIds ?? [])],
  };
}

function indicator(value: unknown): value is CoreIndicatorInstance {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<CoreIndicatorInstance>;
  const ids = ['sma', 'ema', 'rsi', 'macd', 'bollinger', 'atr', 'vwap', 'bull-market-band', 'death-cross', 'ema-stack', 'fair-value-gap', 'golden-cross', 'ideal-bb', 'log-macd', 'macd-dema', 'rsi-divergence', 'stochastic-rsi', 'swing-liquidity', 'volume-profile'];
  if (!item.id || !ids.includes(item.id)) return false;
  if (typeof item.period !== 'number' || !Number.isInteger(item.period) || item.period < 1) return false;
  if (typeof item.enabled !== 'boolean') return false;
  if (item.visible !== undefined && typeof item.visible !== 'boolean') return false;
  for (const optionalPeriod of [item.fastPeriod, item.slowPeriod, item.signalPeriod]) {
    if (optionalPeriod !== undefined && (!Number.isInteger(optionalPeriod) || optionalPeriod < 1)) return false;
  }
  if (item.standardDeviations !== undefined && (!Number.isFinite(item.standardDeviations) || item.standardDeviations <= 0)) return false;
  if (item.anchorTime !== undefined && item.anchorTime !== null && typeof item.anchorTime !== 'string') return false;
  if (item.style !== undefined) {
    if (!item.style || typeof item.style !== 'object') return false;
    const style = item.style as CoreIndicatorStyle;
    if (style.lineWidth !== undefined && (!Number.isInteger(style.lineWidth) || style.lineWidth < 1 || style.lineWidth > 4)) return false;
    for (const [key, visible] of Object.entries(style.plots ?? {})) {
      if (!key || typeof visible !== 'boolean') return false;
    }
    for (const [key, lineStyle] of Object.entries(style.lineStyles ?? {})) {
      if (!key || !['solid', 'dotted', 'dashed', 'large-dashed', 'sparse-dotted'].includes(lineStyle)) return false;
    }
    for (const [key, color] of Object.entries(style.colors ?? {})) {
      if (!key || typeof color !== 'string' || !/^#[0-9a-f]{6}$/i.test(color)) return false;
    }
    if (style.backgroundVisible !== undefined && typeof style.backgroundVisible !== 'boolean') return false;
    if (style.backgroundColor !== undefined && (typeof style.backgroundColor !== 'string' || !/^#[0-9a-f]{6}$/i.test(style.backgroundColor))) return false;
    if (style.precision !== undefined && style.precision !== null && (!Number.isInteger(style.precision) || style.precision < 0 || style.precision > 8)) return false;
    for (const statusLineOption of [style.labelsOnPriceScale, style.valuesInStatusLine, style.inputsInStatusLine]) {
      if (statusLineOption !== undefined && typeof statusLineOption !== 'boolean') return false;
    }
  }
  return true;
}

function parseCharts(value: unknown): TradingChartState[] | null {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_TRADING_CHARTS) return null;
  const chartTypes = TRADING_CHART_TYPE_OPTIONS.map((option) => option.value);
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

function parsePanels(value: unknown): TradingPanelState {
  if (!value || typeof value !== 'object') return { right: true, bottom: true };
  const panels = value as Partial<TradingPanelState>;
  return {
    right: typeof panels.right === 'boolean' ? panels.right : true,
    bottom: typeof panels.bottom === 'boolean' ? panels.bottom : true,
  };
}

function parseFavorites(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item): item is string => typeof item === 'string' && item.length > 0))].slice(0, 500);
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

function migrateCryptoChartsToBinance(charts: TradingChartState[]): TradingChartState[] {
  return charts.map((chart) => {
    const instrumentId = binanceInstrumentIdFor(chart.instrumentId);
    return instrumentId === chart.instrumentId
      ? chart
      : { ...chart, instrumentId, bindingId: null };
  });
}

function migrateCryptoFavoritesToBinance(value: unknown): string[] {
  return [...new Set(parseFavorites(value).map(binanceInstrumentIdFor))];
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
    const migratedCharts = migrateCryptoChartsToBinance(visibleCharts);
    const activeChartId = visibleCharts.some((chart) => chart.chartId === requestedActive)
      ? requestedActive
      : migratedCharts[0].chartId;
    return {
      schemaVersion: 3,
      name: typeof payload.name === 'string' ? payload.name : 'Main Workspace',
      layout: migrateLegacyLayout(legacyLayout),
      activeChartId,
      charts: migratedCharts,
      links: { ...links, visibleRange: false },
      panels: parsePanels(payload.panels),
      favoriteInstrumentIds: migrateCryptoFavoritesToBinance(payload.favoriteInstrumentIds),
    };
  }

  if ((payload.schemaVersion !== 2 && payload.schemaVersion !== 3) || typeof payload.layout !== 'string' || !layouts.includes(payload.layout as TradingLayout)) return null;
  const requestedActive = typeof payload.activeChartId === 'string' ? payload.activeChartId : charts[0].chartId;
  const migratedCharts = migrateCryptoChartsToBinance(charts);
  const migratedLinks = payload.schemaVersion === 2 ? { ...links, visibleRange: false } : links;
  return {
    schemaVersion: 3,
    name: typeof payload.name === 'string' && payload.name.trim() ? payload.name.trim() : 'Main Workspace',
    layout: payload.layout as TradingLayout,
    activeChartId: migratedCharts.some((chart) => chart.chartId === requestedActive) ? requestedActive : migratedCharts[0].chartId,
    charts: migratedCharts,
    links: migratedLinks,
    panels: parsePanels(payload.panels),
    favoriteInstrumentIds: migrateCryptoFavoritesToBinance(payload.favoriteInstrumentIds),
  };
}
