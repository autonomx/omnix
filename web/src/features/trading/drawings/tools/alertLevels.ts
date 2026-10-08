import type { DrawingAlertLevel, DrawingPoint } from './types';

function anchor(point: DrawingPoint): DrawingPoint {
  return { time: point.time, price: point.price };
}

/** A horizontal level at the anchor's price; from the anchor's time onward unless extended left. */
export function horizontalAlertLevel(key: string, label: string, point: DrawingPoint, extendLeft: boolean): DrawingAlertLevel {
  return { key, label, anchors: [anchor(point)], extend: { left: extendLeft, right: true }, interpolation: 'bars' };
}

/** The line through two anchors in bar-index space, ordered by time. Null when both share a time. */
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
  const anchors = firstTime < secondTime ? [anchor(first), anchor(second)] : [anchor(second), anchor(first)];
  return { key, label, anchors, extend: { left: extendLeft, right: extendRight }, interpolation: 'bars' };
}

/**
 * The level's price at a bar index, or null outside its range. `barIndex`
 * maps a time to its (possibly fractional) bar index on the alert's interval;
 * the server evaluates levels the same way.
 */
export function alertLevelPriceAtBar(level: DrawingAlertLevel, index: number, barIndex: (time: string) => number | null): number | null {
  const [first, second] = level.anchors;
  if (!first) return null;
  const firstIndex = barIndex(first.time);
  if (firstIndex === null) return null;
  if (!second) {
    return index < firstIndex && !level.extend.left ? null : first.price;
  }
  const secondIndex = barIndex(second.time);
  if (secondIndex === null || secondIndex === firstIndex) return null;
  if (index < firstIndex && !level.extend.left) return null;
  if (index > secondIndex && !level.extend.right) return null;
  return first.price + (second.price - first.price) * (index - firstIndex) / (secondIndex - firstIndex);
}
