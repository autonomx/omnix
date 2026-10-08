import { tradingIntervalMinutes } from './tradingIntervals';
import type { MarketBar } from './tradingTypes';

/**
 * Bar replay's shared clock (TVP-8.1).
 *
 * Replay has one clock for the whole layout: an epoch-millisecond timestamp.
 * Each chart shows the bars that have closed by then, so charts on different
 * intervals stay in step. Stepping moves the clock to the close of the next
 * (or previous) bar of the active chart.
 *
 * Sub-bar playback (TVP-8.1, after TVP-0.6) will move the clock in steps
 * smaller than one bar; the clock is already a timestamp, so only the step
 * source changes.
 */

/** The nine replay speeds; 1× plays one bar a second. */
export const REPLAY_SPEEDS = [0.1, 0.3, 0.5, 1, 3, 5, 10, 30, 100] as const;

export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

export const DEFAULT_REPLAY_SPEED: ReplaySpeed = 1;

/**
 * The shortest playback tick. Every tick redraws the chart and its
 * indicators, so faster speeds advance several bars per tick instead of
 * ticking faster.
 */
export const REPLAY_MIN_TICK_MS = 100;

export function isReplaySpeed(value: unknown): value is ReplaySpeed {
  return typeof value === 'number' && (REPLAY_SPEEDS as readonly number[]).includes(value);
}

/** The supported speed nearest to `value`; unreadable values give the default. */
export function parseReplaySpeed(value: unknown): ReplaySpeed {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return DEFAULT_REPLAY_SPEED;
  return REPLAY_SPEEDS.reduce<ReplaySpeed>((best, speed) => (
    Math.abs(Math.log(speed / numeric)) < Math.abs(Math.log(best / numeric)) ? speed : best
  ), REPLAY_SPEEDS[0]);
}

export function formatReplaySpeed(speed: ReplaySpeed): string {
  return `${speed}×`;
}

export type ReplayTickPlan = {
  /** Milliseconds between playback ticks. */
  intervalMs: number;
  /** Bars the clock advances per tick. */
  barsPerTick: number;
};

/** How playback ticks at `speed`: `speed` bars a second, never ticking faster than REPLAY_MIN_TICK_MS. */
export function replayTickPlan(speed: ReplaySpeed): ReplayTickPlan {
  const intervalMs = Math.max(REPLAY_MIN_TICK_MS, Math.round(1_000 / speed));
  const barsPerTick = Math.max(1, Math.round(speed * intervalMs / 1_000));
  return { intervalMs, barsPerTick };
}

/**
 * When a bar closes, in epoch milliseconds. An unreadable end time is
 * derived from the start plus the bar's interval; a bar with neither never
 * closes, so replay never reveals it early.
 */
export function barCloseTime(bar: MarketBar): number {
  const end = Date.parse(bar.end_time);
  if (Number.isFinite(end)) return end;
  const start = Date.parse(bar.start_time);
  const minutes = tradingIntervalMinutes(bar.interval ?? '');
  return Number.isFinite(start) && minutes !== null && minutes > 0 ? start + minutes * 60_000 : Number.POSITIVE_INFINITY;
}

/** The clock value that shows `bar` as the latest closed bar. */
export function replayClockForBar(bar: MarketBar): number | null {
  const time = barCloseTime(bar);
  return Number.isFinite(time) ? time : null;
}

/**
 * The close a bar is ordered by. A bar whose close cannot be known counts as
 * closed when the next knowable bar starts (or closes), so it is never shown
 * before a later bar; at the end of the series it never closes. These times
 * never decrease along a time-ordered series, so they can be binary-searched.
 */
function orderingClose(bars: readonly MarketBar[], index: number): number {
  const close = barCloseTime(bars[index]);
  if (Number.isFinite(close)) return close;
  for (let next = index + 1; next < bars.length; next += 1) {
    const start = Date.parse(bars[next].start_time);
    if (Number.isFinite(start)) return start;
    const nextClose = barCloseTime(bars[next]);
    if (Number.isFinite(nextClose)) return nextClose;
  }
  return Number.POSITIVE_INFINITY;
}

/** How many leading bars have an ordering close that passes `accept`. */
function countWhile(bars: readonly MarketBar[], accept: (close: number) => boolean): number {
  let left = 0;
  let right = bars.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (accept(orderingClose(bars, middle))) left = middle + 1;
    else right = middle;
  }
  return left;
}

/** How many of the time-ordered `bars` have closed by `clock`. */
export function replayVisibleCount(bars: readonly MarketBar[], clock: number): number {
  return countWhile(bars, (close) => close <= clock);
}

/** The bars a chart shows at `clock`: those closed by then. */
export function replayVisibleBars(bars: readonly MarketBar[], clock: number): MarketBar[] {
  return bars.slice(0, replayVisibleCount(bars, clock));
}

/** The latest bar closed by `clock`, or null before the first bar closes. */
export function replayBarAtClock(bars: readonly MarketBar[], clock: number): MarketBar | null {
  const count = replayVisibleCount(bars, clock);
  return count > 0 ? bars[count - 1] : null;
}

/**
 * The latest bar closed by `clock` whose close is known, which replay trading
 * can execute against; null when there is none.
 */
export function replayTradableBarAtClock(bars: readonly MarketBar[], clock: number): MarketBar | null {
  for (let index = replayVisibleCount(bars, clock) - 1; index >= 0; index -= 1) {
    if (Number.isFinite(barCloseTime(bars[index]))) return bars[index];
  }
  return null;
}

/**
 * The clock after `steps` bars forward on `bars`, or null when no bar closes
 * after `clock`. Bars that never close are skipped.
 */
export function nextReplayClock(bars: readonly MarketBar[], clock: number, steps = 1): number | null {
  const next = replayVisibleCount(bars, clock);
  for (let target = Math.min(bars.length - 1, next + Math.max(1, Math.trunc(steps)) - 1); target >= next; target -= 1) {
    const close = orderingClose(bars, target);
    if (Number.isFinite(close)) return close;
  }
  return null;
}

/**
 * The clock one bar back on `bars`, never before `floor` (the replay start).
 * Null when the clock is already at or before the floor.
 */
export function previousReplayClock(bars: readonly MarketBar[], clock: number, floor: number): number | null {
  if (clock <= floor) return null;
  const before = countWhile(bars, (close) => close < clock);
  const previous = before > 0 ? orderingClose(bars, before - 1) : null;
  return previous === null || previous < floor ? floor : previous;
}
