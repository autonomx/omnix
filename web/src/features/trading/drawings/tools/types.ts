// Drawing tool registry contract (TVP-0.4).
//
// A drawing tool is one `DrawingToolDefinition`: how it is created, which
// properties it has, and its geometry as renderer-agnostic shapes in screen
// space. Hosts (the SVG overlay, the canvas series primitive) render shapes and
// own input, selection, handles and undo; they never branch on a tool id.

/**
 * A drawing anchor, stored in time/price space, never in pixels. Anchors of a
 * screen-anchored tool (`anchoring: 'screen'`) also carry `screen`, their
 * position as fractions (0-1) of the chart pane; they ignore time and price
 * when drawn. Stored anchors may carry other fields; keep them.
 */
export type DrawingPoint = { time: string; price: number; screen?: { x: number; y: number } };
export type DrawingStyle = { color: string; lineWidth: number; lineStyle: 'solid' | 'dashed' };
export const DEFAULT_DRAWING_STYLE: DrawingStyle = { color: '#66d9e8', lineWidth: 2, lineStyle: 'solid' };

export type ScreenPoint = { x: number; y: number };

/** One record of a list-of-records property, e.g. a fib level `{ value, color, visible }`. */
export type DrawingPropertyRecord = Readonly<Record<string, string | number | boolean>>;
export type DrawingPropertyValue = string | number | boolean | readonly number[] | readonly DrawingPropertyRecord[];
/**
 * Tool properties. Stored values are kept as they are, even when they don't
 * match the schema (a newer or older client may have written them), so
 * geometry reads them defensively (see `properties.ts`).
 */
export type DrawingProperties = Readonly<Record<string, DrawingPropertyValue>>;

export type DrawingRecordField =
  | { key: string; label: string; type: 'number'; min?: number; max?: number; step?: number }
  | { key: string; label: string; type: 'color' }
  | { key: string; label: string; type: 'boolean' }
  | { key: string; label: string; type: 'text' };

/** One editable tool-specific property; drives the generic properties dialog. */
export type DrawingPropertyField =
  | { key: string; label: string; type: 'boolean' }
  | { key: string; label: string; type: 'number'; min?: number; max?: number; step?: number }
  | { key: string; label: string; type: 'number-list'; min?: number; max?: number }
  | { key: string; label: string; type: 'select'; options: readonly { value: string; label: string }[] }
  | { key: string; label: string; type: 'color' }
  | { key: string; label: string; type: 'text' }
  | { key: string; label: string; type: 'records'; fields: readonly DrawingRecordField[]; newRecord: DrawingPropertyRecord };

/**
 * How a drawing is created.
 * - `click`: one anchor on pointer down.
 * - `drag`: two anchors, pointer down to pointer up.
 * - `click-click`: one anchor per click. With `anchors` the drawing completes on
 *   that click; without it, a double click completes it (at least `minAnchors`).
 *   Escape cancels.
 * - `freehand`: anchors follow the pointer while it is down, then are
 *   simplified (Ramer-Douglas-Peucker, `simplifyTolerance` in pixels).
 *
 * `snap: false` opts out of the chart's snap mode and keeps times between
 * bars; freehand defaults to `false`, every other gesture to `true`.
 */
export type DrawingCreation = { snap?: boolean } & (
  | { gesture: 'click' }
  | { gesture: 'drag' }
  | { gesture: 'click-click'; anchors?: number; minAnchors?: number }
  | { gesture: 'freehand'; minAnchors?: number; simplifyTolerance?: number }
);

/** Modifier keys held while an anchor is placed or dragged. */
export type DrawingModifiers = { shift: boolean; alt: boolean; ctrl: boolean };

/** Toolbar group ids of `TradingDrawingTools`. */
export type DrawingToolGroupId =
  | 'cursor'
  | 'lines'
  | 'channels'
  | 'pitchforks'
  | 'fibonacci'
  | 'gann'
  | 'chart-patterns'
  | 'elliott-waves'
  | 'cycles'
  | 'forecasting'
  | 'volume-based'
  | 'measurers'
  | 'brushes'
  | 'arrows'
  | 'shapes'
  | 'text-and-notes';

/**
 * Paint and interaction of one shape.
 * - Colours are CSS colours. An undefined `fill` means no fill, except for text,
 *   where it means the renderer's default text colour.
 * - `className` is a theming hook for the DOM renderer (CSS may refine paint);
 *   every renderer must draw a correct shape from the other fields alone.
 * - `hit: 'none'` marks decoration: it never receives pointer input or hits.
 */
export type ShapePaint = {
  stroke?: string;
  strokeWidth?: number;
  dash?: readonly number[];
  fill?: string;
  fillOpacity?: number;
  opacity?: number;
  className?: string;
  hit?: 'auto' | 'none';
};

export type PathCommand =
  | { op: 'M' | 'L'; x: number; y: number }
  | { op: 'Q'; cx: number; cy: number; x: number; y: number }
  | { op: 'C'; c1x: number; c1y: number; c2x: number; c2y: number; x: number; y: number }
  | { op: 'Z' };

/** The closed set of shapes every renderer supports, in CSS pixels. */
export type DrawingShape =
  | ({ kind: 'segment'; x1: number; y1: number; x2: number; y2: number } & ShapePaint)
  | ({ kind: 'polyline'; points: readonly ScreenPoint[] } & ShapePaint)
  | ({ kind: 'polygon'; points: readonly ScreenPoint[] } & ShapePaint)
  | ({ kind: 'rect'; x: number; y: number; width: number; height: number; radius?: number } & ShapePaint)
  | ({ kind: 'ellipse'; cx: number; cy: number; rx: number; ry: number } & ShapePaint)
  | ({ kind: 'path'; commands: readonly PathCommand[] } & ShapePaint)
  | ({ kind: 'marker'; x: number; y: number; radius: number } & ShapePaint)
  | ({
    kind: 'text';
    x: number;
    y: number;
    text: string;
    align?: 'start' | 'middle' | 'end';
    fontSize?: number;
    fontWeight?: number;
  } & ShapePaint);

export type DrawingShapeKind = DrawingShape['kind'];

/** A loaded bar, as numbers. */
export type DrawingBar = { time: string; open: number; high: number; low: number; close: number; volume: number };

/** The chart's loaded bars, converted on demand. */
export type DrawingBarSeries = {
  readonly length: number;
  at(index: number): DrawingBar | undefined;
  /** Index of the last bar at or before `time`; -1 before the first bar. */
  indexAtOrBefore(time: string): number;
};

export const EMPTY_DRAWING_BARS: DrawingBarSeries = { length: 0, at: () => undefined, indexAtOrBefore: () => -1 };

/** Chart services geometry may use besides the anchors. */
export type DrawingChartAccess = {
  /** Projects any time/price point, e.g. for levels between anchors. */
  project: (point: DrawingPoint) => ScreenPoint | null;
  /** Loaded bars (regression, anchored VWAP, volume profile, bars pattern, P&L). */
  bars: DrawingBarSeries;
  /** The time `count` bars after `time` (fib time zones, cycles); across gaps, and past the data at the bar interval. */
  timeAfterBars: (time: string, count: number) => string | null;
  /** A price as the price scale shows it. */
  formatPrice: (price: number) => string;
};

/** Everything a tool's geometry may depend on. Points are already projected. */
export type DrawingGeometryContext = DrawingChartAccess & {
  /** Anchors in CSS pixels; geometry runs only when every anchor projects. */
  points: readonly ScreenPoint[];
  /** The same anchors in time/price space. */
  rawPoints: readonly DrawingPoint[];
  viewport: { width: number; height: number };
  style: DrawingStyle;
  /** Tool properties; missing ones are filled from the defaults, stored ones kept as they are. */
  properties: DrawingProperties;
  text: string;
  interval: string;
  selected: boolean;
  locked: boolean;
  /** True while the drawing is still being created (anchors may be fewer than the tool's count, see `previewAnchors`). */
  draft: boolean;
};

export type DrawingHit = { distance: number };

/**
 * A level a drawing can alert on (TVP-1.4). Alert lines are straight in
 * bar-index space, as the chart draws them: one anchor is a horizontal level
 * at its price; two anchors are the line through them, interpolated by bar
 * index over the alert's own interval. Without `extend`, a level spans its
 * anchors' times (one anchor: from its time onward when not extended left).
 */
export type DrawingAlertLevel = {
  key: string;
  label: string;
  anchors: readonly DrawingPoint[];
  extend: { left: boolean; right: boolean };
  interpolation: 'bars';
};

/** An action a tool offers in the chart context menu for one of its drawings. */
export type DrawingContextAction = { id: string; label: string };

export type DrawingToolDefinition<Id extends string = string> = {
  id: Id;
  /** Toolbar label; matches a toolbar catalogue entry, which it makes available. */
  label: string;
  /** Name in the object tree when it differs from the label. */
  displayName?: string;
  /** Object tree icon: SVG path data in a 24 x 24 box (a default line icon when absent). */
  icon?: string;
  group: DrawingToolGroupId;
  creation: DrawingCreation;
  /** Screen-anchored tools (anchored note) stay put when the chart pans. */
  anchoring?: 'chart' | 'screen';
  defaultProperties: DrawingProperties;
  propertySchema: readonly DrawingPropertyField[];
  /** The drawing has user-editable text (the header shows a text input; the object tree shows the text). */
  editableText?: boolean;
  /** Text a new drawing starts with. */
  defaultText?: string;
  /** Draft preview while creating: an outline through the anchors (default) or the tool's own shapes. */
  draftPreview?: 'outline' | 'shapes';
  /** With `draftPreview: 'shapes'`, the anchor count (placed + pointer) from which geometry previews; default the tool's minimum. */
  previewAnchors?: number;
  /** Which anchors get edit handles when selected (default `all`; freehand strokes want `ends`). */
  handles?: 'all' | 'ends' | 'none';
  /** Extra class for the edit handles of a selected drawing. */
  handleClassName?: string;
  /** Adjusts a candidate anchor while placing or dragging it (e.g. Shift constrains to 45 degrees). */
  constrain?: (candidate: ScreenPoint, others: readonly ScreenPoint[], modifiers: DrawingModifiers) => ScreenPoint;
  geometry: (context: DrawingGeometryContext) => DrawingShape[];
  /** Overrides the default shape-derived hit test. */
  hitTest?: (shapes: readonly DrawingShape[], point: ScreenPoint, tolerance: number, context: DrawingGeometryContext) => DrawingHit | null;
  /** Levels for drawing alerts; a tool with alert levels offers alerts from its context menu. */
  alertLevels?: (points: readonly DrawingPoint[], properties: DrawingProperties) => DrawingAlertLevel[];
  /** Extra context-menu actions (e.g. a position tool opens the order ticket). */
  contextActions?: readonly DrawingContextAction[];
};

/** Declares a tool and keeps its id as a literal type. */
export function defineDrawingTool<const Id extends string>(definition: DrawingToolDefinition<Id>): DrawingToolDefinition<Id> {
  return definition;
}

/** Indices of the anchors that get edit handles. */
export function handleIndices(definition: Pick<DrawingToolDefinition, 'handles'>, anchors: number): number[] {
  if (definition.handles === 'none' || anchors === 0) return [];
  if (definition.handles === 'ends') return anchors === 1 ? [0] : [0, anchors - 1];
  return Array.from({ length: anchors }, (_, index) => index);
}

export function anchorCount(creation: DrawingCreation): { min: number; max: number | null } {
  switch (creation.gesture) {
    case 'click':
      return { min: 1, max: 1 };
    case 'drag':
      return { min: 2, max: 2 };
    case 'click-click':
      return creation.anchors !== undefined
        ? { min: creation.anchors, max: creation.anchors }
        : { min: creation.minAnchors ?? 2, max: null };
    case 'freehand':
      return { min: creation.minAnchors ?? 2, max: null };
  }
}

/** Whether creation snaps to the chart's snap mode and to bar times. */
export function creationSnaps(creation: DrawingCreation): boolean {
  return creation.snap ?? creation.gesture !== 'freehand';
}
