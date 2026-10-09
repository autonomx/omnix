/**
 * Volume Delta and Cumulative Volume Delta (TVP-6.4), from lower-timeframe bars (TVP-0.6), like TradingView's: each
 * lower bar's volume counts as buying when it closes above its open (or, unchanged, above the previous close) and as
 * selling when below; unchanged bars keep the previous direction. Volume Delta is each chart bar's buying minus selling
 * volume; Cumulative Volume Delta adds it up and restarts each anchor period.
 *
 * The lower bars reach back MAX_INTRABAR_BARS from the latest bar, so older chart bars have no value (TradingView shows
 * the same limit). Computed on the main thread after the bars load, like the external-data indicators.
 */
import { autoIntrabarInterval, groupIntrabars, intrabarRange, isIntrabarInterval, loadIntrabars } from '../intrabarData';
import type { MarketBar } from '../tradingTypes';
import type { CoreIndicatorInstance, IndicatorOutput } from './coreIndicators';
import { sessionClock, sessionPeriods, UTC_SESSION, type TradingSessionSpec } from './tradingSessions';

export const INTRABAR_INDICATOR_IDS = ['tv-volume-delta', 'tv-cumulative-volume-delta'] as const;
export const INTRABAR_REQUIREMENT = 'Reads lower-timeframe bars, up to 5,000 back from the latest bar; older chart bars have no value.';
/** Lower intervals offered besides auto, finest first. */
export const INTRABAR_LOWER_INTERVALS = ['1s', '5s', '15s', '1m', '5m', '15m', '1h', '4h', '1d'] as const;

export function isIntrabarIndicatorId(id: string): boolean {
  return (INTRABAR_INDICATOR_IDS as readonly string[]).includes(id);
}

export type BarDelta = { delta: number; max: number; min: number };

/** Each chart bar's volume delta from its lower bars, by the chart bar's start time (ms). */
export function intrabarDeltas(chartBars: readonly MarketBar[], lowerBars: readonly MarketBar[], interval: string): Map<number, BarDelta> {
  const deltas = new Map<number, BarDelta>();
  let previousClose: number | null = null;
  let direction = 0;
  for (const [start, group] of groupIntrabars(chartBars, lowerBars, interval)) {
    let running = 0;
    let max = 0;
    let min = 0;
    for (const bar of group) {
      const open = Number(bar.open);
      const close = Number(bar.close);
      const volume = Number(bar.volume) || 0;
      if (close > open) direction = 1;
      else if (close < open) direction = -1;
      else if (previousClose !== null && close > previousClose) direction = 1;
      else if (previousClose !== null && close < previousClose) direction = -1;
      running += direction * volume;
      max = Math.max(max, running);
      min = Math.min(min, running);
      previousClose = close;
    }
    deltas.set(start, { delta: running, max, min });
  }
  return deltas;
}

const UP = '#089981';
const DOWN = '#f23645';

/** Volume Delta: a histogram coloured by sign. */
export function volumeDeltaPoints(bars: readonly MarketBar[], deltas: ReadonlyMap<number, BarDelta>): IndicatorOutput['points'] {
  return bars.flatMap((bar) => {
    const value = deltas.get(Date.parse(bar.start_time));
    return value ? [{ time: bar.start_time, value: value.delta, color: value.delta >= 0 ? UP : DOWN }] : [];
  });
}

/** Cumulative Volume Delta: the deltas added up within each anchor period (session day, week or month). */
export function cumulativeVolumeDeltaPoints(
  bars: readonly MarketBar[],
  deltas: ReadonlyMap<number, BarDelta>,
  anchor: 'D' | 'W' | 'M',
  session: TradingSessionSpec = UTC_SESSION,
): IndicatorOutput['points'] {
  const times = bars.map((bar) => Date.parse(bar.start_time));
  const { key } = sessionPeriods(sessionClock(bars, times, session), anchor, session);
  const points: IndicatorOutput['points'] = [];
  let total = 0;
  bars.forEach((bar, index) => {
    if (index === 0 || key[index] !== key[index - 1]) total = 0;
    const value = deltas.get(times[index]);
    if (!value) return;
    total += value.delta;
    points.push({ time: bar.start_time, value: total, color: total >= 0 ? UP : DOWN });
  });
  return points;
}

/** The lower interval an instance reads: its own when it fits the chart interval, else auto. */
export function intrabarLowerInterval(indicator: CoreIndicatorInstance, interval: string): string | null {
  const chosen = indicator.params?.lowerInterval;
  if (typeof chosen === 'string' && chosen !== 'auto' && isIntrabarInterval(interval, chosen)) return chosen;
  return autoIntrabarInterval(interval);
}

export type IntrabarIndicatorContext = { session?: TradingSessionSpec; bindingId?: string | null };

/** The outputs of Volume Delta or Cumulative Volume Delta for the chart's bars; none while the lower bars can't load. */
export async function calculateIntrabarIndicatorOutputs(
  bars: readonly MarketBar[],
  indicator: CoreIndicatorInstance,
  context: IntrabarIndicatorContext = {},
): Promise<IndicatorOutput[]> {
  const id = String(indicator.id);
  const interval = bars[0]?.interval;
  const instrumentId = bars[0]?.instrument_id;
  if (!isIntrabarIndicatorId(id) || !interval || !instrumentId) return [];
  const lowerInterval = intrabarLowerInterval(indicator, interval);
  const range = lowerInterval ? intrabarRange(bars, interval, lowerInterval) : null;
  if (!lowerInterval || !range) return [];
  const response = await loadIntrabars({ instrumentId, bindingId: context.bindingId ?? null, interval, lowerInterval, start: range.start, end: range.end })
    .catch(() => null);
  if (!response) return [];
  const deltas = intrabarDeltas(bars, response.bars as MarketBar[], interval);
  const cumulative = id === 'tv-cumulative-volume-delta';
  const anchor = indicator.params?.anchor === 'W' || indicator.params?.anchor === 'M' ? indicator.params.anchor : 'D';
  const key = cumulative ? `${id}:cvd` : `${id}:delta`;
  const points = cumulative ? cumulativeVolumeDeltaPoints(bars, deltas, anchor, context.session) : volumeDeltaPoints(bars, deltas);
  const output: IndicatorOutput = {
    key,
    title: `${cumulative ? 'CVD' : 'Volume Delta'} (${lowerInterval})`,
    pane: 1,
    kind: 'histogram',
    points,
    visible: indicator.style?.plots?.[key] !== false,
    color: indicator.style?.colors?.[key] ?? UP,
    lineStyle: 'solid',
    lineWidth: indicator.style?.lineWidth ?? 2,
    precision: indicator.style?.precision ?? 0,
    labelsOnPriceScale: true,
    valuesInStatusLine: indicator.style?.valuesInStatusLine ?? true,
    inputsInStatusLine: false,
  };
  return output.visible === false || points.length === 0 ? [] : [output];
}
