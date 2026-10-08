// Drawing tool registry contract (TVP-0.4).
//
// A drawing tool is one `DrawingToolDefinition`: how it is created, which
// properties it has, and its geometry as renderer-agnostic shapes in screen
// space. Hosts (the SVG overlay, the canvas series primitive) render shapes and
// own input, selection, handles and undo; they never branch on a tool id.

/** A drawing anchor. Drawings are stored in time/price space, never in pixels. */
export type DrawingPoint = { time: string; price: number };
export type DrawingStyle = { color: string; lineWidth: number; lineStyle: 'solid' | 'dashed' };
export const DEFAULT_DRAWING_STYLE: DrawingStyle = { color: '#66d9e8', lineWidth: 2, lineStyle: 'solid' };

export type ScreenPoint = { x: number; y: number };

export type DrawingPropertyValue = string | number | boolean | readonly number[];
export type DrawingProperties = Readonly<Record<string, DrawingPropertyValue>>;

/** One editable tool-specific property; drives the generic settings dialog. */
export type DrawingPropertyField =
  | { key: string; label: string; type: 'boolean' }
  | { key: string; label: string; type: 'number'; min?: number; max?: number; step?: number }
  | { key: string; label: string; type: 'number-list'; min?: number; max?: number }
  | { key: string; label: string; type: 'select'; options: readonly { value: string; label: string }[] }
  | { key: string; label: string; type: 'color' }
  | { key: string; label: string; type: 'text' };

/**
 * How a drawing is created.
 * - `click`: one anchor on pointer down.
 * - `drag`: two anchors, pointer down to pointer up.
 * - `click-click`: one anchor per click. With `anchors` the drawing completes on
 *   that click; without it, a double click completes it (at least `minAnchors`).
 * - `freehand`: anchors follow the pointer while it is down, then are
 *   simplified (Ramer-Douglas-Peucker, `simplifyTolerance` in pixels).
 */
export type DrawingCreation =
  | { gesture: 'click' }
  | { gesture: 'drag' }
  | { gesture: 'click-click'; anchors?: number; minAnchors?: number }
  | { gesture: 'freehand'; minAnchors?: number; simplifyTolerance?: number };

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

/** Everything a tool's geometry may depend on. Points are already projected. */
export type DrawingGeometryContext = {
  /** Anchors in CSS pixels; geometry runs only when every anchor projects. */
  points: readonly ScreenPoint[];
  /** The same anchors in time/price space. */
  rawPoints: readonly DrawingPoint[];
  viewport: { width: number; height: number };
  style: DrawingStyle;
  /** Tool properties with defaults filled in. */
  properties: DrawingProperties;
  text: string;
  interval: string;
  selected: boolean;
  locked: boolean;
  /** True while the drawing is still being created. */
  draft: boolean;
  /** Projects any time/price point, e.g. for levels between anchors. */
  project: (point: DrawingPoint) => ScreenPoint | null;
};

export type DrawingHit = { distance: number };

/**
 * A price-over-time line a drawing can alert on (TVP-1.4). The price at time t
 * is `anchor.price + slope * (t - anchor.time)`, for t between `from` and `to`
 * (null = unbounded). The server computes the same values from this object.
 */
export type DrawingAlertLevel = {
  key: string;
  label: string;
  anchor: DrawingPoint;
  /** Price change per millisecond. */
  slope: number;
  from: string | null;
  to: string | null;
};

export type DrawingToolDefinition<Id extends string = string> = {
  id: Id;
  label: string;
  group: DrawingToolGroupId;
  creation: DrawingCreation;
  defaultProperties: DrawingProperties;
  propertySchema: readonly DrawingPropertyField[];
  /** Text a new drawing starts with. */
  defaultText?: string;
  /** Draft preview while creating: an outline through the anchors (default) or the tool's own shapes. */
  draftPreview?: 'outline' | 'shapes';
  /** Which anchors get edit handles when selected (default `all`; freehand strokes want `ends`). */
  handles?: 'all' | 'ends' | 'none';
  /** Extra class for the edit handles of a selected drawing. */
  handleClassName?: string;
  geometry: (context: DrawingGeometryContext) => DrawingShape[];
  /** Overrides the default shape-derived hit test. */
  hitTest?: (shapes: readonly DrawingShape[], point: ScreenPoint, tolerance: number, context: DrawingGeometryContext) => DrawingHit | null;
  /** Price-over-time lines for drawing alerts. */
  alertLevels?: (points: readonly DrawingPoint[], properties: DrawingProperties) => DrawingAlertLevel[];
  /** Anchors handed to the chart's line-alert dialog from the context menu. */
  lineAlertAnchors?: (points: readonly DrawingPoint[]) => DrawingPoint[] | undefined;
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
