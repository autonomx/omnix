// Chart patterns, Elliott waves and cycles (TVP-3.7).
//
// Patterns and waves are labelled polylines through their clicks, with the ratios TradingView shows (retracements
// and extensions measured in price). Cycles repeat the A-B distance in bars across the chart.
import { booleanProperty } from '../properties';
import { areaFill, extendedSegment, lineStroke } from '../shapes';
import { defineDrawingTool, type DrawingGeometryContext, type DrawingPoint, type DrawingShape, type ScreenPoint } from '../types';

function labelAt(context: DrawingGeometryContext, point: ScreenPoint, text: string, above: boolean): DrawingShape {
  return { kind: 'text', x: point.x, y: point.y + (above ? -8 : 18), text, align: 'middle', fontSize: 12, fontWeight: 600, fill: context.style.color, hit: 'none' };
}

/** Whether the point is a local high of the polyline (labels go above highs, below lows). */
function isHigh(points: readonly ScreenPoint[], index: number): boolean {
  const before = points[index - 1];
  const after = points[index + 1];
  const neighbour = before ?? after;
  if (!neighbour) return true;
  // Screen y grows down: a high has the smaller y.
  return points[index].y <= Math.min(before?.y ?? Number.POSITIVE_INFINITY, after?.y ?? Number.POSITIVE_INFINITY);
}

function labelledPolyline(context: DrawingGeometryContext, labels: readonly string[]): DrawingShape[] {
  const stroke = lineStroke(context);
  const points = context.points;
  const shapes: DrawingShape[] = [{ kind: 'polyline', points, ...stroke }];
  points.forEach((point, index) => {
    const text = labels[index];
    if (text) shapes.push(labelAt(context, point, text, isHigh(points, index)));
  });
  return shapes;
}

/** |price move b-c| / |price move a-b| (TradingView's pattern ratios), or null when a-b is flat. */
export function moveRatio(a: DrawingPoint, b: DrawingPoint, c: DrawingPoint, d: DrawingPoint): number | null {
  const base = Math.abs(b.price - a.price);
  return base === 0 ? null : Math.abs(d.price - c.price) / base;
}

function ratioLine(context: DrawingGeometryContext, from: number, to: number, ratio: number | null): DrawingShape[] {
  const a = context.points[from];
  const b = context.points[to];
  if (!a || !b || ratio === null) return [];
  return [
    { kind: 'segment', x1: a.x, y1: a.y, x2: b.x, y2: b.y, ...lineStroke(context), dash: [4, 4], strokeWidth: 1 },
    { kind: 'text', x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 4, text: ratio.toFixed(3), align: 'middle', fontSize: 11, fill: context.style.color, hit: 'none' },
  ];
}

function filledTriangle(context: DrawingGeometryContext, indices: readonly [number, number, number]): DrawingShape[] {
  const points = indices.map((index) => context.points[index]);
  return points.every(Boolean) ? [{ kind: 'polygon', points, ...areaFill(context.style.color), hit: 'none' }] : [];
}

type PatternSpec = {
  anchors: number;
  labels: readonly string[];
  /** Extra shapes once every anchor is placed. */
  extras?: (context: DrawingGeometryContext) => DrawingShape[];
};

function patternTool<const Id extends string>(id: Id, label: string, displayName: string, group: 'chart-patterns' | 'elliott-waves', spec: PatternSpec) {
  return defineDrawingTool({
    id,
    label,
    displayName,
    group,
    creation: { gesture: 'click-click', anchors: spec.anchors },
    draftPreview: 'shapes',
    previewAnchors: 2,
    defaultProperties: { showLabels: true },
    propertySchema: [{ key: 'showLabels', label: 'Labels and ratios', type: 'boolean' }],
    geometry: (context) => {
      const labels = booleanProperty(context.properties, 'showLabels', true) ? spec.labels : [];
      const complete = context.points.length >= spec.anchors;
      const extras = complete && spec.extras && labels.length ? spec.extras(context) : [];
      const fills = extras.filter((shape) => shape.kind === 'polygon');
      return [...fills, ...labelledPolyline(context, labels), ...extras.filter((shape) => shape.kind !== 'polygon')];
    },
  });
}

const raw = (context: DrawingGeometryContext) => context.rawPoints;

export const xabcdPatternTool = patternTool('xabcd-pattern', 'XABCD pattern', 'XABCD Pattern', 'chart-patterns', {
  anchors: 5,
  labels: ['X', 'A', 'B', 'C', 'D'],
  extras: (context) => {
    const [x, a, b, c, d] = raw(context);
    return [
      ...filledTriangle(context, [0, 1, 2]),
      ...filledTriangle(context, [2, 3, 4]),
      ...ratioLine(context, 0, 2, moveRatio(x, a, a, b)),
      ...ratioLine(context, 1, 3, moveRatio(a, b, b, c)),
      ...ratioLine(context, 2, 4, moveRatio(b, c, c, d)),
      ...ratioLine(context, 0, 4, moveRatio(x, a, a, d)),
    ];
  },
});

export const cypherPatternTool = patternTool('cypher-pattern', 'Cypher pattern', 'Cypher Pattern', 'chart-patterns', {
  anchors: 5,
  labels: ['X', 'A', 'B', 'C', 'D'],
  extras: (context) => {
    const [x, a, b, c, d] = raw(context);
    // Cypher ratios: B retraces X-A, C extends X-A (measured X to C), D retraces X-C.
    return [
      ...filledTriangle(context, [0, 1, 2]),
      ...filledTriangle(context, [2, 3, 4]),
      ...ratioLine(context, 0, 2, moveRatio(x, a, a, b)),
      ...ratioLine(context, 0, 3, moveRatio(x, a, x, c)),
      ...ratioLine(context, 2, 4, moveRatio(x, c, c, d)),
    ];
  },
});

export const abcdPatternTool = patternTool('abcd-pattern', 'ABCD pattern', 'ABCD Pattern', 'chart-patterns', {
  anchors: 4,
  labels: ['A', 'B', 'C', 'D'],
  extras: (context) => {
    const [a, b, c, d] = raw(context);
    return [...ratioLine(context, 0, 2, moveRatio(a, b, b, c)), ...ratioLine(context, 1, 3, moveRatio(b, c, c, d))];
  },
});

/** The point where lines a-b and c-d cross, or null when they are parallel. */
export function intersection(a: ScreenPoint, b: ScreenPoint, c: ScreenPoint, d: ScreenPoint): ScreenPoint | null {
  const denominator = (a.x - b.x) * (c.y - d.y) - (a.y - b.y) * (c.x - d.x);
  if (Math.abs(denominator) < 1e-9) return null;
  const t = ((a.x - c.x) * (c.y - d.y) - (a.y - c.y) * (c.x - d.x)) / denominator;
  return { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) };
}

export const trianglePatternTool = patternTool('triangle-pattern', 'Triangle pattern', 'Triangle Pattern', 'chart-patterns', {
  anchors: 4,
  labels: ['A', 'B', 'C', 'D'],
  extras: (context) => {
    // The two sides through A-C and B-D, drawn to where they meet (the apex) when it is ahead.
    const [a, b, c, d] = context.points;
    const apex = intersection(a, c, b, d);
    const stroke = lineStroke(context);
    const right = Math.max(c.x, d.x);
    const end = apex && apex.x > right && apex.x < right + 4 * Math.max(1, right - Math.min(a.x, b.x)) ? apex : null;
    const upper = end ?? extendedSegment(a, c, context.viewport, false, false)[1];
    const lower = end ?? extendedSegment(b, d, context.viewport, false, false)[1];
    return [
      { kind: 'polygon', points: [a, upper, ...(end ? [] : [lower]), b], ...areaFill(context.style.color), hit: 'none' },
      { kind: 'segment', x1: a.x, y1: a.y, x2: upper.x, y2: upper.y, ...stroke, dash: [4, 4], strokeWidth: 1 },
      { kind: 'segment', x1: b.x, y1: b.y, x2: lower.x, y2: lower.y, ...stroke, dash: [4, 4], strokeWidth: 1 },
    ];
  },
});

export const threeDrivesPatternTool = patternTool('three-drives-pattern', 'Three drives pattern', 'Three Drives Pattern', 'chart-patterns', {
  anchors: 7,
  labels: ['', '1', '', '2', '', '3', ''],
  extras: (context) => {
    const p = raw(context);
    // Each correction against its drive, and each drive against the one before.
    return [
      ...ratioLine(context, 1, 3, moveRatio(p[0], p[1], p[1], p[2])),
      ...ratioLine(context, 3, 5, moveRatio(p[2], p[3], p[3], p[4])),
      ...ratioLine(context, 2, 4, moveRatio(p[1], p[2], p[2], p[3])),
      ...ratioLine(context, 4, 6, moveRatio(p[3], p[4], p[4], p[5])),
    ];
  },
});

export const headAndShouldersTool = patternTool('head-and-shoulders', 'Head and shoulders', 'Head and Shoulders', 'chart-patterns', {
  anchors: 7,
  labels: ['', 'Left shoulder', '', 'Head', '', 'Right shoulder', ''],
  extras: (context) => {
    // The neckline through the two troughs (anchors 3 and 5), across the pattern and beyond.
    const [, , left, , right] = context.points;
    const [start, end] = extendedSegment(left, right, context.viewport, false, true);
    return [
      { kind: 'segment', x1: start.x, y1: start.y, x2: end.x, y2: end.y, ...lineStroke(context), dash: [6, 4] },
      { kind: 'text', x: (left.x + right.x) / 2, y: (left.y + right.y) / 2 + 16, text: 'Neckline', align: 'middle', fontSize: 11, fill: context.style.color, hit: 'none' },
    ];
  },
});

export const elliottImpulseTool = patternTool('elliott-impulse-wave', 'Elliott impulse wave (1·2·3·4·5)', 'Elliott Impulse Wave', 'elliott-waves', {
  anchors: 6,
  labels: ['0', '(1)', '(2)', '(3)', '(4)', '(5)'],
});

export const elliottCorrectionTool = patternTool('elliott-correction-wave', 'Elliott correction wave (A·B·C)', 'Elliott Correction Wave', 'elliott-waves', {
  anchors: 4,
  labels: ['0', '(A)', '(B)', '(C)'],
});

export const elliottTriangleTool = patternTool('elliott-triangle-wave', 'Elliott triangle wave (A·B·C·D·E)', 'Elliott Triangle Wave', 'elliott-waves', {
  anchors: 6,
  labels: ['0', '(A)', '(B)', '(C)', '(D)', '(E)'],
});

export const elliottDoubleComboTool = patternTool('elliott-double-combo-wave', 'Elliott double combo wave (W·X·Y)', 'Elliott Double Combo Wave', 'elliott-waves', {
  anchors: 4,
  labels: ['0', '(W)', '(X)', '(Y)'],
});

export const elliottTripleComboTool = patternTool('elliott-triple-combo-wave', 'Elliott triple combo wave (W·X·Y·X·Z)', 'Elliott Triple Combo Wave', 'elliott-waves', {
  anchors: 6,
  labels: ['0', '(W)', '(X)', '(Y)', '(X)', '(Z)'],
});

// Cycles.

/** The x of each multiple of the A-B bar distance from A across the viewport (both ways), at most `limit`. */
function cycleXs(context: DrawingGeometryContext, limit = 200): number[] {
  const [first, second] = context.rawPoints;
  const start = context.barIndexForTime(first.time);
  const end = context.barIndexForTime(second.time);
  if (start === null || end === null || end === start) return [context.points[0].x];
  const step = Math.abs(end - start);
  const xs: number[] = [];
  for (let n = -limit; n <= limit && xs.length < limit; n += 1) {
    const time = context.timeForBarIndex(start + step * n);
    const at = time ? context.project({ time, price: first.price }) : null;
    if (at && at.x >= -1 && at.x <= context.viewport.width + 1) xs.push(at.x);
  }
  return xs;
}

export const cyclicLinesTool = defineDrawingTool({
  id: 'cyclic-lines',
  label: 'Cyclic lines',
  displayName: 'Cyclic Lines',
  group: 'cycles',
  creation: { gesture: 'drag' },
  defaultProperties: {},
  propertySchema: [],
  geometry: (context) => cycleXs(context).map((x): DrawingShape => ({ kind: 'segment', x1: x, y1: 0, x2: x, y2: context.viewport.height, ...lineStroke(context) })),
});

export const timeCyclesTool = defineDrawingTool({
  id: 'time-cycles',
  label: 'Time cycles',
  displayName: 'Time Cycles',
  group: 'cycles',
  creation: { gesture: 'drag' },
  defaultProperties: { fill: true },
  propertySchema: [{ key: 'fill', label: 'Background', type: 'boolean' }],
  geometry: (context) => {
    // Half circles on A's level, each one A-B wide, repeating across the chart.
    const [first] = context.points;
    const xs = cycleXs(context).sort((x, y) => x - y);
    const fill = booleanProperty(context.properties, 'fill', true) ? areaFill(context.style.color) : {};
    const shapes: DrawingShape[] = [];
    for (let index = 0; index < xs.length - 1; index += 1) {
      const radius = (xs[index + 1] - xs[index]) / 2;
      const center = xs[index] + radius;
      const points = Array.from({ length: 33 }, (_, step) => {
        const angle = Math.PI + Math.PI * step / 32;
        return { x: center + Math.cos(angle) * radius, y: first.y + Math.sin(angle) * radius };
      });
      shapes.push({ kind: 'polygon', points, ...lineStroke(context), ...fill });
    }
    return shapes;
  },
});

export const sineLineTool = defineDrawingTool({
  id: 'sine-line',
  label: 'Sine line',
  displayName: 'Sine Line',
  group: 'cycles',
  creation: { gesture: 'drag' },
  defaultProperties: {},
  propertySchema: [],
  geometry: (context) => {
    // A at a crest, B at the next trough: half a period between them, across the whole chart.
    const [crest, trough] = context.points;
    const half = trough.x - crest.x;
    if (Math.abs(half) < 1) return [{ kind: 'segment', x1: crest.x, y1: crest.y, x2: trough.x, y2: trough.y, ...lineStroke(context) }];
    const middle = (crest.y + trough.y) / 2;
    const amplitude = (crest.y - trough.y) / 2;
    const step = Math.max(2, Math.min(Math.abs(half) / 16, 8));
    const points: ScreenPoint[] = [];
    for (let x = 0; x <= context.viewport.width; x += step) points.push({ x, y: middle + amplitude * Math.cos(Math.PI * (x - crest.x) / half) });
    return [{ kind: 'polyline', points, ...lineStroke(context) }];
  },
});
