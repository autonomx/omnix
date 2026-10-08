// Channels (TVP-3.1): parallel channel, flat top/bottom and disjoint channel.
//
// Each is three clicks: two anchors for the first line, a third that places the
// other line. Geometry is in screen space; alert levels are two-anchor lines in
// time/price (straight in bar-index space, see `barTimeline.ts`).
import { alertLevelPriceAt, lineAlertLevel, lineThroughPoint } from '../alertLevels';
import { booleanProperty } from '../properties';
import { areaFill, extendedSegment, lineStroke } from '../shapes';
import {
  anchorHandle,
  defineDrawingTool,
  type DrawingAlertExtend,
  type DrawingAlertLevel,
  type DrawingGeometryContext,
  type DrawingHandleDrag,
  type DrawingPoint,
  type DrawingProperties,
  type DrawingPropertyField,
  type DrawingShape,
  type DrawingToolServices,
  type ScreenPoint,
} from '../types';

const EXTEND_FIELDS: readonly DrawingPropertyField[] = [
  { key: 'extendLeft', label: 'Extend left', type: 'boolean' },
  { key: 'extendRight', label: 'Extend right', type: 'boolean' },
  { key: 'fill', label: 'Background', type: 'boolean' },
];

function extendOf(properties: DrawingProperties): DrawingAlertExtend {
  const left = booleanProperty(properties, 'extendLeft', false);
  const right = booleanProperty(properties, 'extendRight', false);
  return left && right ? 'both' : left ? 'left' : right ? 'right' : 'none';
}

/** The y of the line `first`-`second` at `x` (the first anchor's y for a vertical line). */
export function lineYAt(first: ScreenPoint, second: ScreenPoint, x: number): number {
  const dx = second.x - first.x;
  return Math.abs(dx) < 0.0001 ? first.y : first.y + (second.y - first.y) * (x - first.x) / dx;
}

function line(context: DrawingGeometryContext, first: ScreenPoint, second: ScreenPoint, extra: Partial<DrawingShape> = {}): DrawingShape {
  const [start, end] = extendedSegment(
    first,
    second,
    context.viewport,
    booleanProperty(context.properties, 'extendLeft', false),
    booleanProperty(context.properties, 'extendRight', false),
  );
  return { kind: 'segment', x1: start.x, y1: start.y, x2: end.x, y2: end.y, ...lineStroke(context), ...extra } as DrawingShape;
}

function band(context: DrawingGeometryContext, corners: readonly ScreenPoint[]): DrawingShape[] {
  if (!booleanProperty(context.properties, 'fill', true)) return [];
  return [{ kind: 'polygon', points: corners, ...areaFill(context.style.color) }];
}

const shift = (point: ScreenPoint, dy: number): ScreenPoint => ({ x: point.x, y: point.y + dy });

/** The price of `level`'s infinite line at `time`'s bar index. */
function priceAt(level: DrawingAlertLevel, time: string, services: Pick<DrawingToolServices, 'barIndexForTime'>): number | null {
  const index = services.barIndexForTime(time);
  return index === null ? null : alertLevelPriceAt(level, index, services.barIndexForTime, true);
}

/**
 * Moves anchor `index` of the channel's first line and keeps the channel's width: the third anchor stays at its
 * time, at the same price distance from the moved line as before.
 */
export function moveKeepingWidth({ points, point, services }: Pick<DrawingHandleDrag, 'points' | 'point' | 'services'>, index: 0 | 1): DrawingPoint[] {
  const next = points.map((existing, position) => (position === index ? { ...existing, ...point } : existing));
  const [first, second, third] = points;
  const before = first && second ? lineAlertLevel('base', '', first, second, 'none') : null;
  const after = next[0] && next[1] ? lineAlertLevel('base', '', next[0], next[1], 'none') : null;
  const was = before && third ? priceAt(before, third.time, services) : null;
  const now = after && third ? priceAt(after, third.time, services) : null;
  if (third && was !== null && now !== null) next[2] = { ...third, price: now + (third.price - was) };
  return next;
}

export const parallelChannelTool = defineDrawingTool({
  id: 'parallel-channel',
  label: 'Parallel channel',
  group: 'channels',
  creation: { gesture: 'click-click', anchors: 3 },
  defaultProperties: { extendLeft: false, extendRight: false, fill: true, showMiddle: true },
  propertySchema: [...EXTEND_FIELDS, { key: 'showMiddle', label: 'Middle line', type: 'boolean' }],
  draftPreview: 'shapes',
  previewAnchors: 2,
  // The first line's anchors keep the width; the third anchor sets it.
  handles: (context) => context.points.map((position, index) => (index < 2 && context.points.length === 3
    ? { ...anchorHandle(index, position), drag: (input: DrawingHandleDrag) => ({ points: moveKeepingWidth(input, index as 0 | 1) }) }
    : anchorHandle(index, position))),
  geometry: (context) => {
    const [first, second, third] = context.points;
    if (!third) return [line(context, first, second)];
    const dy = third.y - lineYAt(first, second, third.x);
    const shapes = [
      ...band(context, [first, second, shift(second, dy), shift(first, dy)]),
      line(context, first, second),
      line(context, shift(first, dy), shift(second, dy)),
    ];
    if (booleanProperty(context.properties, 'showMiddle', true)) {
      shapes.push(line(context, shift(first, dy / 2), shift(second, dy / 2), { dash: [4, 4], strokeWidth: 1 }));
    }
    return shapes;
  },
  alertLevels: ([first, second, third], properties, services) => {
    if (!first || !second || !third) return [];
    const base = lineAlertLevel('base', 'Channel line', first, second, extendOf(properties));
    if (!base) return [];
    const onBase = priceAt(base, third.time, services);
    const parallelAbove = onBase !== null && third.price > onBase;
    const relabel = (level: DrawingAlertLevel, upper: boolean) => ({ ...level, key: upper ? 'upper' : 'lower', label: upper ? 'Upper line' : 'Lower line' });
    const levels: DrawingAlertLevel[] = [relabel(base, !parallelAbove)];
    const parallel = lineThroughPoint('parallel', 'Parallel line', base, third, services);
    if (parallel) levels.push(relabel(parallel, parallelAbove));
    if (onBase !== null && booleanProperty(properties, 'showMiddle', true)) {
      const middle = lineThroughPoint('middle', 'Middle line', base, { time: third.time, price: (third.price + onBase) / 2 }, services);
      if (middle) levels.push(middle);
    }
    return levels;
  },
});

export const flatTopBottomTool = defineDrawingTool({
  id: 'flat-top-bottom',
  label: 'Flat top/bottom',
  group: 'channels',
  creation: { gesture: 'click-click', anchors: 3 },
  defaultProperties: { extendLeft: false, extendRight: false, fill: true },
  propertySchema: EXTEND_FIELDS,
  draftPreview: 'shapes',
  previewAnchors: 2,
  geometry: (context) => {
    const [first, second, third] = context.points;
    if (!third) return [line(context, first, second)];
    const flatFirst = { x: first.x, y: third.y };
    const flatSecond = { x: second.x, y: third.y };
    return [...band(context, [first, second, flatSecond, flatFirst]), line(context, first, second), line(context, flatFirst, flatSecond)];
  },
  alertLevels: ([first, second, third], properties) => {
    if (!first || !second || !third) return [];
    const extend = extendOf(properties);
    return [
      lineAlertLevel('trend', 'Trend line', first, second, extend),
      lineAlertLevel('flat', 'Flat line', { time: first.time, price: third.price }, { time: second.time, price: third.price }, extend),
    ].filter((level): level is DrawingAlertLevel => level !== null);
  },
});

/** The disjoint channel's second line: from the third anchor, with the first line's slope mirrored. */
function mirroredSecond(first: DrawingPoint, second: DrawingPoint, third: DrawingPoint): DrawingPoint {
  return { time: second.time, price: third.price - (second.price - first.price) };
}

export const disjointChannelTool = defineDrawingTool({
  id: 'disjoint-channel',
  label: 'Disjoint channel',
  group: 'channels',
  creation: { gesture: 'click-click', anchors: 3 },
  defaultProperties: { extendLeft: false, extendRight: false, fill: true },
  propertySchema: EXTEND_FIELDS,
  draftPreview: 'shapes',
  previewAnchors: 2,
  geometry: (context) => {
    const [first, second, third] = context.points;
    if (!third) return [line(context, first, second)];
    const otherFirst = { x: first.x, y: third.y };
    const otherSecond = { x: second.x, y: third.y - (second.y - first.y) };
    return [...band(context, [first, second, otherSecond, otherFirst]), line(context, first, second), line(context, otherFirst, otherSecond)];
  },
  alertLevels: ([first, second, third], properties) => {
    if (!first || !second || !third) return [];
    const extend = extendOf(properties);
    return [
      lineAlertLevel('first', 'First line', first, second, extend),
      lineAlertLevel('second', 'Second line', { time: first.time, price: third.price }, mirroredSecond(first, second, third), extend),
    ].filter((level): level is DrawingAlertLevel => level !== null);
  },
});
