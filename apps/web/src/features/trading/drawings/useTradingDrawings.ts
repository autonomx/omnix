import { useEffect, useRef, useState } from 'react';
import { tradingApi } from '../tradingApi';
import type { TradingDocument } from '../tradingTypes';
import {
  addDrawing,
  deleteSelectedDrawing,
  emptyDrawingState,
  moveDrawingPoint,
  redoDrawing,
  replaceDrawings,
  selectDrawing,
  undoDrawing,
  type DrawingPoint,
  type DrawingState,
  type TradingDrawing,
} from './drawingCommands';

function recordId(instrumentId: string): string {
  return `instrument-${instrumentId.replace(/[^a-zA-Z0-9._-]+/g, '-')}`;
}

export function useTradingDrawings(instrumentId: string) {
  const [state, setState] = useState<DrawingState>(emptyDrawingState);
  const [status, setStatus] = useState<'loading' | 'saved' | 'saving' | 'conflict' | 'error'>('loading');
  const recordRef = useRef<TradingDocument | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState(emptyDrawingState());
    setStatus('loading');
    void tradingApi.documents('drawings').then((records) => {
      if (cancelled) return;
      const record = records.find((item) => item.record_id === recordId(instrumentId)) ?? null;
      recordRef.current = record;
      const payload = record?.payload as { drawings?: TradingDrawing[] } | undefined;
      const drawings = Array.isArray(payload?.drawings) ? payload.drawings.filter((item) => item.instrumentId === instrumentId) : [];
      setState(replaceDrawings(drawings));
      setStatus('saved');
    }).catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, [instrumentId]);

  const persist = (next: DrawingState) => {
    setState(next);
    setStatus('saving');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        const payload = { instrumentId, drawings: next.drawings.map((drawing) => ({ ...drawing, selected: false })) };
        const record = recordRef.current;
        const saved = record
          ? await tradingApi.updateDocument('drawings', record, payload)
          : await tradingApi.createDocument('drawings', recordId(instrumentId), payload);
        recordRef.current = saved;
        setStatus('saved');
      } catch (error) {
        setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
      }
    }, 450);
  };

  return {
    state,
    status,
    add: (drawing: TradingDrawing) => persist(addDrawing(state, drawing)),
    select: (id: string | null) => setState(selectDrawing(state, id)),
    movePoint: (id: string, index: number, point: DrawingPoint) => persist(moveDrawingPoint(state, id, index, point)),
    removeSelected: () => persist(deleteSelectedDrawing(state)),
    undo: () => persist(undoDrawing(state)),
    redo: () => persist(redoDrawing(state)),
  };
}
