import { drawingPropertiesWithDefaults, type DrawingToolId } from './tools/registry';
import { DEFAULT_DRAWING_STYLE, type DrawingEditPatch, type DrawingPoint, type DrawingProperties, type DrawingStyle } from './tools/types';
import type { DrawingVisibility } from './drawingVisibility';

export { DEFAULT_DRAWING_STYLE };
export type { DrawingPoint, DrawingProperties, DrawingStyle };

/** A toolbar tool: the registered drawing tools (`tools/registry.ts`) plus three modes. */
export type DrawingTool = 'cursor' | 'alert' | 'eraser' | DrawingToolId;
export type DrawingSnapMode = 'none' | 'time' | 'price' | 'ohlc';
export type TradingDrawing = {
  drawingId: string;
  instrumentId: string;
  toolType: Exclude<DrawingTool, 'cursor' | 'alert' | 'eraser'>;
  points: DrawingPoint[];
  selected: boolean;
  revision: number;
  style?: DrawingStyle;
  locked?: boolean;
  hidden?: boolean;
  text?: string;
  /** Tool-specific properties (fib levels, extensions, ...); defaults come from the tool definition. */
  properties?: DrawingProperties;
  /** Which intervals the drawing shows on (TVP-3.8); every interval when absent. */
  visibility?: DrawingVisibility;
};

export type DrawingState = {
  drawings: TradingDrawing[];
  /** The primary selected drawing (handles, properties, the header's controls); one of `selectedIds`. */
  selectedId: string | null;
  /** Every selected drawing (Ctrl+click adds and removes, TVP-2.2); moves, deletes and copies act on all of them. */
  selectedIds?: readonly string[];
  history: TradingDrawing[][];
  future: TradingDrawing[][];
  /** The merge key of the last edit; another edit with the same key joins its undo step. */
  lastEditKey?: string | null;
};

export const emptyDrawingState = (): DrawingState => ({ drawings: [], selectedId: null, selectedIds: [], history: [], future: [] });

/** The selected drawings' ids, primary last. */
export function selectedDrawingIds(state: DrawingState): readonly string[] {
  return state.selectedIds ?? (state.selectedId ? [state.selectedId] : []);
}

function withSelection(state: DrawingState, ids: readonly string[], primary: string | null): DrawingState {
  const present = new Set(state.drawings.map((drawing) => drawing.drawingId));
  const selected = [...new Set(ids.filter((id) => present.has(id)))];
  const main = primary && selected.includes(primary) ? primary : selected.at(-1) ?? null;
  const ordered = main ? [...selected.filter((id) => id !== main), main] : selected;
  const chosen = new Set(ordered);
  return {
    ...state,
    selectedId: main,
    selectedIds: ordered,
    drawings: state.drawings.map((drawing) => (drawing.selected === chosen.has(drawing.drawingId) ? drawing : { ...drawing, selected: chosen.has(drawing.drawingId) })),
  };
}

export function normalizeDrawing(drawing: TradingDrawing): TradingDrawing {
  return {
    ...drawing,
    points: drawing.points.map((point) => ({ ...point })),
    style: { ...DEFAULT_DRAWING_STYLE, ...(drawing.style ?? {}) },
    locked: drawing.locked ?? false,
    hidden: drawing.hidden ?? false,
    text: drawing.text ?? '',
    properties: drawingPropertiesWithDefaults(drawing.toolType, drawing.properties),
  };
}

/** Copies for the undo history: selection is not part of a drawing's history, so copies are unselected. */
function copyAll(drawings: TradingDrawing[]): TradingDrawing[] {
  return drawings.map((drawing) => ({ ...normalizeDrawing(drawing), selected: false }));
}

function snapshot(state: DrawingState, mergeKey?: string): DrawingState {
  if (mergeKey !== undefined && state.lastEditKey === mergeKey) return { ...state, future: [] };
  return { ...state, history: [...state.history, copyAll(state.drawings)], future: [], lastEditKey: mergeKey ?? null };
}

export function replaceDrawings(drawings: TradingDrawing[]): DrawingState {
  return { drawings: drawings.map((drawing) => ({ ...normalizeDrawing(drawing), selected: false })), selectedId: null, selectedIds: [], history: [], future: [] };
}

export function addDrawing(state: DrawingState, drawing: TradingDrawing): DrawingState {
  const next = snapshot(state);
  return withSelection({ ...next, drawings: [...next.drawings, normalizeDrawing(drawing)] }, [drawing.drawingId], drawing.drawingId);
}

export function selectDrawing(state: DrawingState, drawingId: string | null): DrawingState {
  return withSelection(state, drawingId ? [drawingId] : [], drawingId);
}

/** Ctrl+click: adds a drawing to the selection (it becomes the primary one) or removes it. */
export function toggleDrawingSelection(state: DrawingState, drawingId: string): DrawingState {
  const current = selectedDrawingIds(state);
  return current.includes(drawingId)
    ? withSelection(state, current.filter((id) => id !== drawingId), null)
    : withSelection(state, [...current, drawingId], drawingId);
}

function shiftPoints(points: readonly DrawingPoint[], from: DrawingPoint, to: DrawingPoint): DrawingPoint[] {
  const timeDelta = Date.parse(to.time) - Date.parse(from.time);
  const priceDelta = to.price - from.price;
  return points.map((point) => ({
    ...point,
    time: new Date(Date.parse(point.time) + timeDelta).toISOString(),
    price: point.price + priceDelta,
    ...(point.screen && from.screen && to.screen
      ? { screen: { x: point.screen.x + to.screen.x - from.screen.x, y: point.screen.y + to.screen.y - from.screen.y } }
      : {}),
  }));
}

/** The drawings a gesture on `drawingId` acts on: the whole selection when it is part of one, else that drawing. */
export function drawingGroup(state: DrawingState, drawingId: string): readonly string[] {
  const selection = selectedDrawingIds(state);
  return selection.length > 1 && selection.includes(drawingId) ? selection : [drawingId];
}

/** Applies a tool handle's edit (anchors and/or properties) as one undo step. */
export function editDrawing(state: DrawingState, drawingId: string, patch: DrawingEditPatch): DrawingState {
  const target = state.drawings.find((drawing) => drawing.drawingId === drawingId);
  if (!target || target.locked || (!patch.points && !patch.properties)) return state;
  const next = snapshot(state);
  return {
    ...next,
    drawings: next.drawings.map((drawing) => drawing.drawingId !== drawingId ? drawing : {
      ...drawing,
      revision: drawing.revision + 1,
      points: patch.points ? patch.points.map((point) => ({ ...point })) : drawing.points,
      properties: patch.properties
        ? drawingPropertiesWithDefaults(drawing.toolType, { ...drawing.properties, ...patch.properties })
        : drawing.properties,
    }),
  };
}

export function moveDrawingPoint(state: DrawingState, drawingId: string, pointIndex: number, point: DrawingPoint): DrawingState {
  const target = state.drawings.find((drawing) => drawing.drawingId === drawingId);
  if (target?.locked) return state;
  const next = snapshot(state);
  return {
    ...next,
    drawings: next.drawings.map((drawing) => drawing.drawingId !== drawingId ? drawing : {
      ...drawing,
      revision: drawing.revision + 1,
      points: drawing.points.map((existing, index) => index === pointIndex ? point : existing),
    }),
  };
}

/**
 * Moves a drawing by `from` -> `to`, as one undo step. When the drawing is part of a multi-selection the whole
 * selection moves (locked drawings stay). Moves with the same `mergeKey` in a row share one undo step.
 */
export function translateDrawing(
  state: DrawingState,
  drawingId: string,
  from: DrawingPoint,
  to: DrawingPoint,
  mergeKey?: string,
): DrawingState {
  const fromTime = Date.parse(from.time);
  const toTime = Date.parse(to.time);
  if (!Number.isFinite(fromTime) || !Number.isFinite(toTime)) return state;
  if (fromTime === toTime && from.price === to.price && from.screen?.x === to.screen?.x && from.screen?.y === to.screen?.y) return state;
  const group = new Set(drawingGroup(state, drawingId));
  const movable = state.drawings.filter((drawing) => group.has(drawing.drawingId) && !drawing.locked);
  if (movable.length === 0) return state;
  const moving = new Set(movable.map((drawing) => drawing.drawingId));
  const next = snapshot(state, mergeKey);
  return {
    ...next,
    drawings: next.drawings.map((drawing) => !moving.has(drawing.drawingId) ? drawing : {
      ...drawing,
      revision: drawing.revision + 1,
      points: shiftPoints(drawing.points, from, to),
    }),
  };
}

/** Copies of `drawingIds`, moved by `from` -> `to`, added and selected as one undo step (Ctrl+drag clone, paste). */
export function cloneDrawings(
  state: DrawingState,
  drawingIds: readonly string[],
  from: DrawingPoint,
  to: DrawingPoint,
  makeId: () => string = () => crypto.randomUUID(),
): DrawingState {
  const sources = state.drawings.filter((drawing) => drawingIds.includes(drawing.drawingId));
  if (sources.length === 0) return state;
  const copies = sources.map((drawing) => ({ ...normalizeDrawing(drawing), drawingId: makeId(), revision: 1, locked: false, hidden: false, points: shiftPoints(drawing.points, from, to) }));
  const next = snapshot(state);
  return withSelection({ ...next, drawings: [...next.drawings, ...copies] }, copies.map((copy) => copy.drawingId), copies.at(-1)?.drawingId ?? null);
}

/** Pastes copied drawings onto `instrumentId`'s chart at their own times and prices, selected, as one undo step. */
export function pasteDrawings(
  state: DrawingState,
  drawings: readonly TradingDrawing[],
  instrumentId: string,
  makeId: () => string = () => crypto.randomUUID(),
): DrawingState {
  if (drawings.length === 0) return state;
  const copies = drawings.map((drawing) => ({ ...normalizeDrawing(drawing), drawingId: makeId(), instrumentId, revision: 1, locked: false, hidden: false }));
  const next = snapshot(state);
  return withSelection({ ...next, drawings: [...next.drawings, ...copies] }, copies.map((copy) => copy.drawingId), copies.at(-1)?.drawingId ?? null);
}

export function updateSelectedDrawing(
  state: DrawingState,
  patch: Partial<Pick<TradingDrawing, 'style' | 'locked' | 'hidden' | 'text' | 'properties' | 'visibility'>>,
  /** Edits with the same key in a row are one undo step (e.g. one settings field while it is edited). */
  mergeKey?: string,
): DrawingState {
  if (!state.selectedId) return state;
  const next = snapshot(state, mergeKey === undefined ? undefined : `${state.selectedId}:${mergeKey}`);
  return {
    ...next,
    drawings: next.drawings.map((drawing) => drawing.drawingId !== state.selectedId ? drawing : {
      ...drawing,
      ...patch,
      style: patch.style ? { ...drawing.style, ...patch.style } as DrawingStyle : drawing.style,
      properties: patch.properties
        ? drawingPropertiesWithDefaults(drawing.toolType, { ...drawing.properties, ...patch.properties })
        : drawing.properties,
      revision: drawing.revision + 1,
    }),
  };
}

/** Deletes every selected drawing, as one undo step. */
export function deleteSelectedDrawing(state: DrawingState): DrawingState {
  const selection = new Set(selectedDrawingIds(state));
  if (!state.drawings.some((drawing) => selection.has(drawing.drawingId))) return state;
  const next = snapshot(state);
  return withSelection({ ...next, drawings: next.drawings.filter((drawing) => !selection.has(drawing.drawingId)) }, [], null);
}

export function deleteDrawing(state: DrawingState, drawingId: string): DrawingState {
  if (!state.drawings.some((drawing) => drawing.drawingId === drawingId)) return state;
  const next = snapshot(state);
  const remaining = { ...next, drawings: next.drawings.filter((drawing) => drawing.drawingId !== drawingId) };
  return withSelection(remaining, selectedDrawingIds(state).filter((id) => id !== drawingId), state.selectedId === drawingId ? null : state.selectedId);
}

export function deleteAllDrawings(state: DrawingState): DrawingState {
  if (state.drawings.length === 0) return state;
  const next = snapshot(state);
  return { ...next, drawings: [], selectedId: null, selectedIds: [] };
}

export function undoDrawing(state: DrawingState): DrawingState {
  const previous = state.history.at(-1);
  if (!previous) return state;
  return {
    drawings: copyAll(previous),
    selectedId: null,
    selectedIds: [],
    history: state.history.slice(0, -1),
    future: [copyAll(state.drawings), ...state.future],
  };
}

export function redoDrawing(state: DrawingState): DrawingState {
  const next = state.future[0];
  if (!next) return state;
  return {
    drawings: copyAll(next),
    selectedId: null,
    selectedIds: [],
    history: [...state.history, copyAll(state.drawings)],
    future: state.future.slice(1),
  };
}

export function snapDrawingPoint(point: DrawingPoint, mode: DrawingSnapMode): DrawingPoint {
  if (mode === 'none') return point;
  const milliseconds = Date.parse(point.time);
  const snappedTime = mode === 'time' || mode === 'ohlc'
    ? new Date(Math.round(milliseconds / 60_000) * 60_000).toISOString()
    : point.time;
  const snappedPrice = mode === 'price' || mode === 'ohlc'
    ? Math.round(point.price * 100) / 100
    : point.price;
  return { time: snappedTime, price: snappedPrice };
}
