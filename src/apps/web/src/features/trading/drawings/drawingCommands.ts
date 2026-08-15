export type DrawingPoint = { time: string; price: number };
export type DrawingTool =
  | 'cursor'
  | 'alert'
  | 'horizontal-line'
  | 'trend-line'
  | 'vertical-line'
  | 'ray'
  | 'rectangle'
  | 'fibonacci'
  | 'text'
  | 'measurement';
export type DrawingSnapMode = 'none' | 'time' | 'price' | 'ohlc';
export type DrawingStyle = { color: string; lineWidth: number; lineStyle: 'solid' | 'dashed' };
export type TradingDrawing = {
  drawingId: string;
  instrumentId: string;
  toolType: Exclude<DrawingTool, 'cursor' | 'alert'>;
  points: DrawingPoint[];
  selected: boolean;
  revision: number;
  style?: DrawingStyle;
  locked?: boolean;
  hidden?: boolean;
  text?: string;
};

export type DrawingState = {
  drawings: TradingDrawing[];
  selectedId: string | null;
  history: TradingDrawing[][];
  future: TradingDrawing[][];
};

export const DEFAULT_DRAWING_STYLE: DrawingStyle = { color: '#66d9e8', lineWidth: 2, lineStyle: 'solid' };
export const emptyDrawingState = (): DrawingState => ({ drawings: [], selectedId: null, history: [], future: [] });

function normalize(drawing: TradingDrawing): TradingDrawing {
  return {
    ...drawing,
    points: drawing.points.map((point) => ({ ...point })),
    style: { ...DEFAULT_DRAWING_STYLE, ...(drawing.style ?? {}) },
    locked: drawing.locked ?? false,
    hidden: drawing.hidden ?? false,
    text: drawing.text ?? '',
  };
}

function cloneDrawings(drawings: TradingDrawing[]): TradingDrawing[] {
  return drawings.map(normalize);
}

function snapshot(state: DrawingState): DrawingState {
  return { ...state, history: [...state.history, cloneDrawings(state.drawings)], future: [] };
}

export function replaceDrawings(drawings: TradingDrawing[]): DrawingState {
  return { drawings: drawings.map((drawing) => ({ ...normalize(drawing), selected: false })), selectedId: null, history: [], future: [] };
}

export function addDrawing(state: DrawingState, drawing: TradingDrawing): DrawingState {
  const next = snapshot(state);
  return { ...next, drawings: [...next.drawings.map((item) => ({ ...item, selected: false })), { ...normalize(drawing), selected: true }], selectedId: drawing.drawingId };
}

export function selectDrawing(state: DrawingState, drawingId: string | null): DrawingState {
  return { ...state, selectedId: drawingId, drawings: state.drawings.map((drawing) => ({ ...drawing, selected: drawing.drawingId === drawingId })) };
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

export function translateDrawing(
  state: DrawingState,
  drawingId: string,
  from: DrawingPoint,
  to: DrawingPoint,
): DrawingState {
  const target = state.drawings.find((drawing) => drawing.drawingId === drawingId);
  if (!target || target.locked) return state;
  const fromTime = Date.parse(from.time);
  const toTime = Date.parse(to.time);
  if (!Number.isFinite(fromTime) || !Number.isFinite(toTime)) return state;
  const timeDelta = toTime - fromTime;
  const priceDelta = to.price - from.price;
  if (timeDelta === 0 && priceDelta === 0) return state;
  const next = snapshot(state);
  return {
    ...next,
    drawings: next.drawings.map((drawing) => drawing.drawingId !== drawingId ? drawing : {
      ...drawing,
      revision: drawing.revision + 1,
      points: drawing.points.map((point) => ({
        time: new Date(Date.parse(point.time) + timeDelta).toISOString(),
        price: point.price + priceDelta,
      })),
    }),
  };
}

export function updateSelectedDrawing(
  state: DrawingState,
  patch: Partial<Pick<TradingDrawing, 'style' | 'locked' | 'hidden' | 'text'>>,
): DrawingState {
  if (!state.selectedId) return state;
  const next = snapshot(state);
  return {
    ...next,
    drawings: next.drawings.map((drawing) => drawing.drawingId !== state.selectedId ? drawing : {
      ...drawing,
      ...patch,
      style: patch.style ? { ...drawing.style, ...patch.style } as DrawingStyle : drawing.style,
      revision: drawing.revision + 1,
    }),
  };
}

export function deleteSelectedDrawing(state: DrawingState): DrawingState {
  if (!state.selectedId) return state;
  const next = snapshot(state);
  return { ...next, drawings: next.drawings.filter((drawing) => drawing.drawingId !== state.selectedId), selectedId: null };
}

export function deleteAllDrawings(state: DrawingState): DrawingState {
  if (state.drawings.length === 0) return state;
  const next = snapshot(state);
  return { ...next, drawings: [], selectedId: null };
}

export function undoDrawing(state: DrawingState): DrawingState {
  const previous = state.history.at(-1);
  if (!previous) return state;
  return {
    drawings: cloneDrawings(previous),
    selectedId: null,
    history: state.history.slice(0, -1),
    future: [cloneDrawings(state.drawings), ...state.future],
  };
}

export function redoDrawing(state: DrawingState): DrawingState {
  const next = state.future[0];
  if (!next) return state;
  return {
    drawings: cloneDrawings(next),
    selectedId: null,
    history: [...state.history, cloneDrawings(state.drawings)],
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
