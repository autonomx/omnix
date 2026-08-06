export type DrawingPoint = { time: string; price: number };
export type DrawingTool = 'cursor' | 'horizontal-line' | 'trend-line';
export type TradingDrawing = {
  drawingId: string;
  instrumentId: string;
  toolType: Exclude<DrawingTool, 'cursor'>;
  points: DrawingPoint[];
  selected: boolean;
  revision: number;
};

export type DrawingState = {
  drawings: TradingDrawing[];
  selectedId: string | null;
  history: TradingDrawing[][];
  future: TradingDrawing[][];
};

export const emptyDrawingState = (): DrawingState => ({ drawings: [], selectedId: null, history: [], future: [] });

function snapshot(state: DrawingState): DrawingState {
  return { ...state, history: [...state.history, state.drawings.map((drawing) => ({ ...drawing, points: drawing.points.map((point) => ({ ...point })) }))], future: [] };
}

export function replaceDrawings(drawings: TradingDrawing[]): DrawingState {
  return { drawings: drawings.map((drawing) => ({ ...drawing, selected: false })), selectedId: null, history: [], future: [] };
}

export function addDrawing(state: DrawingState, drawing: TradingDrawing): DrawingState {
  const next = snapshot(state);
  return { ...next, drawings: [...next.drawings.map((item) => ({ ...item, selected: false })), { ...drawing, selected: true }], selectedId: drawing.drawingId };
}

export function selectDrawing(state: DrawingState, drawingId: string | null): DrawingState {
  return { ...state, selectedId: drawingId, drawings: state.drawings.map((drawing) => ({ ...drawing, selected: drawing.drawingId === drawingId })) };
}

export function moveDrawingPoint(state: DrawingState, drawingId: string, pointIndex: number, point: DrawingPoint): DrawingState {
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

export function deleteSelectedDrawing(state: DrawingState): DrawingState {
  if (!state.selectedId) return state;
  const next = snapshot(state);
  return { ...next, drawings: next.drawings.filter((drawing) => drawing.drawingId !== state.selectedId), selectedId: null };
}

export function undoDrawing(state: DrawingState): DrawingState {
  const previous = state.history.at(-1);
  if (!previous) return state;
  return {
    drawings: previous,
    selectedId: null,
    history: state.history.slice(0, -1),
    future: [state.drawings, ...state.future],
  };
}

export function redoDrawing(state: DrawingState): DrawingState {
  const next = state.future[0];
  if (!next) return state;
  return {
    drawings: next,
    selectedId: null,
    history: [...state.history, state.drawings],
    future: state.future.slice(1),
  };
}
