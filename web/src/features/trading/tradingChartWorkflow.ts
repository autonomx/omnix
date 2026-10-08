/** Pure helpers for the chart workflow items of TVP-2.5: bar countdown, extended hours, go to date, clipboard, market status and chart templates. */
import { TRADING_CHART_TYPE_OPTIONS, type TradingChartType, type TradingPaneHit } from './chart/chartAdapter';
import type { CoreIndicatorId, CoreIndicatorInstance } from './indicators/coreIndicators';
import { parseChartSettings, parseIndicatorInstances } from './persistence/workspaceDocument';
import { isIntradayInterval, tradingIntervalDurationMs } from './tradingIntervals';
import type { TradingChartSettings } from './tradingStore';
import type { MarketBar, TradingDocument } from './tradingTypes';
import { zonedDateTimeToUtc } from './tradingTime';

// ---------------------------------------------------------------- bar countdown

type BarTimes = Pick<MarketBar, 'start_time' | 'end_time'>;

/** When a bar closes: its end time, or its start plus the interval when the end is missing. */
export function barCloseTime(bar: BarTimes, interval: string): number | null {
  const start = Date.parse(bar.start_time);
  const end = Date.parse(bar.end_time);
  if (Number.isFinite(end) && (!Number.isFinite(start) || end > start)) return end;
  const duration = tradingIntervalDurationMs(interval);
  return Number.isFinite(start) && duration !== null ? start + duration : null;
}

/** Milliseconds until the bar closes; null once it has closed or when it has no close time. */
export function barCountdownRemainingMs(bar: BarTimes | undefined, interval: string, nowMs: number): number | null {
  if (!bar) return null;
  const close = barCloseTime(bar, interval);
  if (close === null) return null;
  const remaining = close - nowMs;
  return remaining > 0 ? remaining : null;
}

const pad = (value: number) => String(value).padStart(2, '0');

/** `mm:ss` under an hour, `hh:mm:ss` under a day, then `Nd hh:mm`. Rounds up so a bar never shows 00:00 before it closes. */
export function formatBarCountdown(remainingMs: number): string {
  const total = Math.max(0, Math.ceil(remainingMs / 1_000));
  const days = Math.floor(total / 86_400);
  const hours = Math.floor((total % 86_400) / 3_600);
  const minutes = Math.floor((total % 3_600) / 60);
  const seconds = total % 60;
  if (days > 0) return `${days}d ${pad(hours)}:${pad(minutes)}`;
  if (hours > 0) return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  return `${pad(minutes)}:${pad(seconds)}`;
}

/** The countdown shows by default on intraday intervals; tick and range bars have no close time. */
export function barCountdownEnabled(settings: TradingChartSettings | undefined, interval: string): boolean {
  if (tradingIntervalDurationMs(interval) === null) return false;
  return settings?.barCountdown ?? isIntradayInterval(interval);
}

// ---------------------------------------------------------------- extended hours

export type ExtendedSession = 'pre' | 'post';

export function extendedSessionOf(bar: Pick<MarketBar, 'session'>): ExtendedSession | null {
  if (bar.session === 'extended_pre') return 'pre';
  if (bar.session === 'extended_post') return 'post';
  return null;
}

export function hasExtendedHoursBars(bars: readonly Pick<MarketBar, 'session'>[]): boolean {
  return bars.some((bar) => extendedSessionOf(bar) !== null);
}

/** Bars with pre- and post-market bars removed when extended hours are hidden. */
export function filterExtendedHours<T extends Pick<MarketBar, 'session'>>(bars: readonly T[], showExtendedHours: boolean): T[] {
  return showExtendedHours ? [...bars] : bars.filter((bar) => extendedSessionOf(bar) === null);
}

export type ExtendedPriceLine = { price: number; session: ExtendedSession; time: string };

/** The latest pre/post-market price when the newest bar is outside the regular session. */
export function extendedSessionPriceLine(bars: readonly MarketBar[]): ExtendedPriceLine | null {
  const latest = bars.at(-1);
  if (!latest) return null;
  const session = extendedSessionOf(latest);
  const price = Number(latest.close);
  if (!session || !Number.isFinite(price)) return null;
  return { price, session, time: latest.start_time };
}

// ---------------------------------------------------------------- pane maximise / collapse

export type PaneDoubleClickAction =
  | { type: 'toggle-indicator-fullscreen'; id: CoreIndicatorId }
  | { type: 'toggle-indicator-minimized'; id: CoreIndicatorId }
  | { type: 'toggle-main-fullscreen' };

/**
 * Double-click maximises the pane under the pointer and restores it on the next double-click;
 * Ctrl (or Cmd) + double-click collapses an indicator pane. The main pane only maximises when
 * there are indicator panes to hide, and it can't collapse.
 */
export function paneDoubleClickAction(
  pane: TradingPaneHit | null,
  modifier: boolean,
  state: { indicatorPaneCount: number; mainPaneFullscreen: boolean; fullscreenIndicator: CoreIndicatorId | null },
): PaneDoubleClickAction | null {
  if (!pane) return null;
  if (pane.kind === 'indicator') {
    if (modifier) return state.fullscreenIndicator === pane.id ? null : { type: 'toggle-indicator-minimized', id: pane.id };
    return { type: 'toggle-indicator-fullscreen', id: pane.id };
  }
  if (modifier) return null;
  return state.indicatorPaneCount > 0 || state.mainPaneFullscreen ? { type: 'toggle-main-fullscreen' } : null;
}

// ---------------------------------------------------------------- go to date

/** A `YYYY-MM-DD` or `YYYY-MM-DDTHH:mm` value in the chart timezone, as a UTC timestamp. */
export function parseGoToDate(value: string, timeZone: string): number | null {
  return zonedDateTimeToUtc(value.trim(), timeZone);
}

/** The bar containing a time: the last bar that starts at or before it, or -1 before the first bar. */
export function barIndexAtTime(bars: readonly Pick<MarketBar, 'start_time'>[], timeMs: number): number {
  let low = 0;
  let high = bars.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (Date.parse(bars[middle].start_time) <= timeMs) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

export const MAX_CHART_HISTORY_LIMIT = 5_000;

export type GoToDatePlan =
  | { kind: 'scroll'; index: number }
  | { kind: 'load-history'; limit: number }
  | { kind: 'unavailable'; earliest: string | null };

/**
 * What going to a time needs: a scroll to the bar holding it, more history (a larger bar limit on
 * the existing bars request), or nothing more to load. The extra history is estimated from the
 * loaded bars' average spacing, which accounts for sessions and weekends.
 */
export function planGoToDate(
  bars: readonly Pick<MarketBar, 'start_time'>[],
  targetMs: number,
  currentLimit: number,
  maxLimit = MAX_CHART_HISTORY_LIMIT,
): GoToDatePlan {
  if (bars.length === 0) return { kind: 'unavailable', earliest: null };
  const first = Date.parse(bars[0].start_time);
  if (targetMs >= first) return { kind: 'scroll', index: Math.max(0, barIndexAtTime(bars, targetMs)) };
  if (currentLimit >= maxLimit) return { kind: 'unavailable', earliest: bars[0].start_time };
  const last = Date.parse(bars[bars.length - 1].start_time);
  const spacing = bars.length > 1 ? Math.max(1, (last - first) / (bars.length - 1)) : 60_000;
  const needed = Math.ceil(((last - targetMs) / spacing) * 1.15) + 50;
  return { kind: 'load-history', limit: Math.min(maxLimit, Math.max(currentLimit * 2, needed)) };
}

/** A logical range that keeps the current zoom and centres a bar. */
export function centeredLogicalRange(
  index: number,
  current: { from: number; to: number } | null,
): { from: number; to: number } {
  const width = current && Number.isFinite(current.to - current.from) && current.to > current.from
    ? current.to - current.from
    : 120;
  return { from: index - width / 2, to: index + width / 2 };
}

// ---------------------------------------------------------------- clipboard

export function dataUrlToBlob(dataUrl: string): Blob {
  const match = /^data:([^;,]+)?(;base64)?,(.*)$/s.exec(dataUrl);
  if (!match) throw new Error('Not a data URL');
  const type = match[1] ?? 'application/octet-stream';
  if (!match[2]) return new Blob([decodeURIComponent(match[3])], { type });
  const binary = atob(match[3]);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], { type });
}

/** Writes a PNG data URL to the clipboard as an image. Throws when the browser can't. */
export async function copyImageDataUrlToClipboard(
  dataUrl: string,
  clipboard: Pick<Clipboard, 'write'> | undefined = typeof navigator === 'undefined' ? undefined : navigator.clipboard,
  ClipboardItemType: typeof ClipboardItem | undefined = typeof ClipboardItem === 'undefined' ? undefined : ClipboardItem,
): Promise<void> {
  if (!clipboard?.write || !ClipboardItemType) throw new Error('This browser cannot copy images to the clipboard.');
  const blob = dataUrlToBlob(dataUrl);
  await clipboard.write([new ClipboardItemType({ [blob.type || 'image/png']: blob })]);
}

// ---------------------------------------------------------------- market status and data delay

export type MarketStatusValue = 'open' | 'pre_market' | 'post_market' | 'closed' | 'unknown';

export function marketStatusLabel(status: MarketStatusValue, alwaysOpen: boolean): string | null {
  if (status === 'open') return alwaysOpen ? 'Market open 24/7' : 'Market open';
  if (status === 'pre_market') return 'Pre-market';
  if (status === 'post_market') return 'Post-market';
  if (status === 'closed') return 'Market closed';
  return null;
}

/** A delayed-data badge when the feed binding or the dataset reports delayed data. */
export function dataDelayLabel(
  binding: { delay_seconds?: number | null } | null | undefined,
  provenance: { delay_seconds?: number | null; freshness_mode?: string | null } | null | undefined,
): string | null {
  const delay = Math.max(binding?.delay_seconds ?? 0, provenance?.delay_seconds ?? 0);
  if (delay > 0) {
    return delay >= 60 ? `Delayed ${Math.round(delay / 60)} min` : `Delayed ${Math.round(delay)} s`;
  }
  return provenance?.freshness_mode === 'delayed' ? 'Delayed' : null;
}

// ---------------------------------------------------------------- chart templates

/** Chart templates share the indicator-preset documents, marked with this kind. */
export const CHART_TEMPLATE_KIND = 'chart-template';

export type ChartTemplate = {
  recordId: string;
  name: string;
  chartType: TradingChartType;
  settings: TradingChartSettings;
  indicators: CoreIndicatorInstance[];
};

/** A template holds the chart's style and indicators, never its symbol or interval. */
export function chartTemplatePayload(input: {
  name: string;
  chartType: TradingChartType;
  settings?: TradingChartSettings;
  indicators: readonly CoreIndicatorInstance[];
}): Record<string, unknown> {
  return {
    name: input.name.trim() || 'Chart template',
    templateKind: CHART_TEMPLATE_KIND,
    templateVersion: 1,
    formulaVersion: 'omnix-indicators-v2',
    chartType: input.chartType,
    settings: { ...(input.settings ?? {}) },
    indicators: input.indicators.map((indicator) => ({ ...indicator })),
  };
}

export function parseChartTemplate(record: Pick<TradingDocument, 'record_id' | 'payload' | 'status'>): ChartTemplate | null {
  if (record.status !== 'active') return null;
  const payload = record.payload as Record<string, unknown>;
  if (payload.templateKind !== CHART_TEMPLATE_KIND) return null;
  const chartType = TRADING_CHART_TYPE_OPTIONS.find((option) => option.value === payload.chartType)?.value;
  const indicators = parseIndicatorInstances(payload.indicators);
  const settings = parseChartSettings(payload.settings);
  if (!chartType || !indicators || !settings) return null;
  return {
    recordId: record.record_id,
    name: typeof payload.name === 'string' && payload.name.trim() ? payload.name.trim() : record.record_id,
    chartType,
    settings,
    indicators,
  };
}

export function chartTemplateRecordId(name: string, now = Date.now()): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48) || 'chart';
  return `template-${slug}-${now}`;
}
