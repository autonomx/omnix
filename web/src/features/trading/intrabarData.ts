/**
 * Intrabar data (TVP-0.6): lower-timeframe bars inside chart bars, for volume delta (TVP-6.4) and sub-bar replay
 * (TVP-8.1). The server reads them from the latest bars of the lower interval, so a range further back than the
 * provider reaches comes back partial (`complete` false, `available_from` where the data starts).
 */
import type { components } from './api/generated';
import { tradingApi } from './tradingApi';
import { tradingIntervalDurationMs } from './tradingIntervals';
import type { MarketBar } from './tradingTypes';

export type IntrabarResponse = components['schemas']['IntrabarResponse'];
export type IntrabarRequest = {
  instrumentId: string;
  bindingId?: string | null;
  /** The chart's interval. */
  interval: string;
  lowerInterval: string;
  /** Epoch milliseconds; the bars starting in [start, end). */
  start: number;
  end: number;
};

/** The most lower bars the server returns for one request. */
export const MAX_INTRABAR_BARS = 5_000;

/**
 * The lower interval read inside a chart interval when the user leaves it on auto, like TradingView's volume delta:
 * seconds charts read 1s, intraday charts 1m, daily charts 5m... kept so a few hundred chart bars fit the budget.
 */
export function autoIntrabarInterval(interval: string): string | null {
  const ms = tradingIntervalDurationMs(interval);
  if (ms === null || ms <= 1_000) return null;
  if (ms < 60_000) return '1s';
  if (ms <= 3_600_000) return '1m';
  if (ms < 86_400_000) return '5m';
  if (ms < 7 * 86_400_000) return '1h';
  return '1d';
}

/** Whether `lowerInterval` fits inside `interval`: shorter, and a whole number of times. */
export function isIntrabarInterval(interval: string, lowerInterval: string): boolean {
  const chart = tradingIntervalDurationMs(interval);
  const lower = tradingIntervalDurationMs(lowerInterval);
  return chart !== null && lower !== null && lower > 0 && lower < chart && chart % lower === 0;
}

/** The [start, end) range of chart bars whose lower bars fit one request, keeping the latest bars. */
export function intrabarRange(bars: readonly MarketBar[], interval: string, lowerInterval: string): { start: number; end: number } | null {
  const lower = tradingIntervalDurationMs(lowerInterval);
  const chart = tradingIntervalDurationMs(interval);
  if (bars.length === 0 || lower === null || chart === null) return null;
  const end = Date.parse(bars[bars.length - 1].start_time) + chart;
  const earliest = end - MAX_INTRABAR_BARS * lower;
  const first = bars.find((bar) => Date.parse(bar.start_time) >= earliest);
  return first ? { start: Date.parse(first.start_time), end } : null;
}

const cache = new Map<string, Promise<IntrabarResponse>>();
const CACHE_LIMIT = 32;

function cacheKey(request: IntrabarRequest): string {
  return [request.instrumentId, request.bindingId ?? '', request.interval, request.lowerInterval, request.start, request.end].join('|');
}

/** Loads (once per instrument, feed, intervals and range) the lower bars; a failed load is not cached. */
export function loadIntrabars(request: IntrabarRequest): Promise<IntrabarResponse> {
  const key = cacheKey(request);
  const cached = cache.get(key);
  if (cached) return cached;
  const pending = tradingApi.intrabars(request).catch((error: unknown) => {
    cache.delete(key);
    throw error;
  });
  cache.set(key, pending);
  // Oldest first: a Map keeps insertion order.
  while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value!);
  return pending;
}

/** Forgets cached loads (tests, or a feed change). */
export function clearIntrabarCache(): void {
  cache.clear();
}

/** The lower bars of each chart bar, by the chart bar's start time (ms); lower bars outside every chart bar are dropped. */
export function groupIntrabars(chartBars: readonly MarketBar[], lowerBars: readonly MarketBar[], interval: string): Map<number, MarketBar[]> {
  const groups = new Map<number, MarketBar[]>();
  const chartMs = tradingIntervalDurationMs(interval);
  if (chartMs === null) return groups;
  const starts = chartBars.map((bar) => Date.parse(bar.start_time));
  let index = 0;
  for (const lower of [...lowerBars].sort((a, b) => Date.parse(a.start_time) - Date.parse(b.start_time))) {
    const time = Date.parse(lower.start_time);
    while (index + 1 < starts.length && starts[index + 1] <= time) index += 1;
    const start = starts[index];
    if (start === undefined || time < start) continue;
    const end = Date.parse(chartBars[index].end_time);
    if (time >= (Number.isFinite(end) ? end : start + chartMs)) continue;
    const group = groups.get(start) ?? [];
    group.push(lower);
    groups.set(start, group);
  }
  return groups;
}

/**
 * The chart bar as it stood at `clock`: its lower bars that closed by then, combined (open of the first, high and
 * low over them, close of the last, volume summed). Null before the first lower bar closes.
 */
export function formingBar(chartBar: MarketBar, lowerBars: readonly MarketBar[], clock: number): MarketBar | null {
  const closed = lowerBars.filter((bar) => Date.parse(bar.end_time) <= clock);
  if (closed.length === 0) return null;
  let high = Number(closed[0].high);
  let low = Number(closed[0].low);
  let volume = 0;
  for (const bar of closed) {
    high = Math.max(high, Number(bar.high));
    low = Math.min(low, Number(bar.low));
    volume += Number(bar.volume);
  }
  const last = closed[closed.length - 1];
  return {
    ...chartBar,
    open: closed[0].open,
    high: String(high),
    low: String(low),
    close: last.close,
    volume: String(volume),
    is_final: Date.parse(chartBar.end_time) <= clock,
  };
}
