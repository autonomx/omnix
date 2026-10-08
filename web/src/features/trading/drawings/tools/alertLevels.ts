import type { DrawingAlertLevel, DrawingPoint } from './types';

/** A level at one price for every time from `from` (null = always). */
export function horizontalAlertLevel(key: string, label: string, point: DrawingPoint, from: string | null): DrawingAlertLevel {
  return { key, label, anchor: { ...point }, slope: 0, from, to: null };
}

/**
 * The line through two anchors, bounded by them unless extended. Returns null
 * when both anchors share a time (a vertical line has no price over time).
 */
export function lineAlertLevel(
  key: string,
  label: string,
  first: DrawingPoint,
  second: DrawingPoint,
  extendLeft: boolean,
  extendRight: boolean,
): DrawingAlertLevel | null {
  const firstTime = Date.parse(first.time);
  const secondTime = Date.parse(second.time);
  if (!Number.isFinite(firstTime) || !Number.isFinite(secondTime) || firstTime === secondTime) return null;
  const [left, right] = firstTime < secondTime ? [first, second] : [second, first];
  return {
    key,
    label,
    anchor: { ...first },
    slope: (second.price - first.price) / (secondTime - firstTime),
    from: extendLeft ? null : new Date(Date.parse(left.time)).toISOString(),
    to: extendRight ? null : new Date(Date.parse(right.time)).toISOString(),
  };
}

/** The level's price at `time`, or null outside its time range. */
export function alertLevelPrice(level: DrawingAlertLevel, time: string): number | null {
  const at = Date.parse(time);
  if (!Number.isFinite(at)) return null;
  if (level.from !== null && at < Date.parse(level.from)) return null;
  if (level.to !== null && at > Date.parse(level.to)) return null;
  return level.anchor.price + level.slope * (at - Date.parse(level.anchor.time));
}
