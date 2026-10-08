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

/** When a bar closes, in epoch milliseconds (its start when the end is unreadable). */
export function barCloseTime(bar: MarketBar): number {
  const end = Date.parse(bar.end_time);
  return Number.isFinite(end) ? end : Date.parse(bar.start_time);
}

/** The clock value that shows `bar` as the latest closed bar. */
export function replayClockForBar(bar: MarketBar): number | null {
  const time = barCloseTime(bar);
  return Number.isFinite(time) ? time : null;
}

/** How many of the time-ordered `bars` have closed by `clock`. */
export function replayVisibleCount(bars: readonly MarketBar[], clock: number): number {
  let left = 0;
  let right = bars.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (barCloseTime(bars[middle]) <= clock) left = middle + 1;
    else right = middle;
  }
  return left;
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

/** The clock after `steps` bars forward on `bars`, or null when no bar closes after `clock`. */
export function nextReplayClock(bars: readonly MarketBar[], clock: number, steps = 1): number | null {
  const next = replayVisibleCount(bars, clock);
  if (next >= bars.length) return null;
  const target = Math.min(bars.length - 1, next + Math.max(1, Math.trunc(steps)) - 1);
  return barCloseTime(bars[target]);
}

/**
 * The clock one bar back on `bars`, never before `floor` (the replay start).
 * Null when the clock is already at or before the floor.
 */
export function previousReplayClock(bars: readonly MarketBar[], clock: number, floor: number): number | null {
  if (clock <= floor) return null;
  let left = 0;
  let right = bars.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (barCloseTime(bars[middle]) < clock) left = middle + 1;
    else right = middle;
  }
  const previous = left > 0 ? barCloseTime(bars[left - 1]) : null;
  return previous === null || previous < floor ? floor : previous;
}
