import { useEffect, useState } from 'react';
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
  translateDrawing,
  undoDrawing,
  updateSelectedDrawing,
  type DrawingPoint,
  type DrawingState,
  type DrawingStyle,
  type TradingDrawing,
} from './drawingCommands';

export type DrawingPersistenceStatus = 'loading' | 'saved' | 'saving' | 'conflict' | 'error';

type DrawingSnapshot = {
  state: DrawingState;
  status: DrawingPersistenceStatus;
  serverState: DrawingState | null;
};

type DrawingEntry = DrawingSnapshot & {
  instrumentId: string;
  record: TradingDocument | null;
  timer: ReturnType<typeof setTimeout> | null;
  listeners: Set<() => void>;
  loadPromise: Promise<void> | null;
  loaded: boolean;
};

const entries = new Map<string, DrawingEntry>();

function recordId(instrumentId: string): string {
  return `instrument-${instrumentId.replace(/[^a-zA-Z0-9._-]+/g, '-')}`;
}

function entryFor(instrumentId: string): DrawingEntry {
  const existing = entries.get(instrumentId);
  if (existing) return existing;
  const created: DrawingEntry = {
    instrumentId,
    state: emptyDrawingState(),
    status: 'loading',
    serverState: null,
    record: null,
    timer: null,
    listeners: new Set(),
    loadPromise: null,
    loaded: false,
  };
  entries.set(instrumentId, created);
  return created;
}

function snapshot(entry: DrawingEntry): DrawingSnapshot {
  return { state: entry.state, status: entry.status, serverState: entry.serverState };
}

function emit(entry: DrawingEntry): void {
  entry.listeners.forEach((listener) => listener());
}

function drawingsFrom(record: TradingDocument | null, instrumentId: string): TradingDrawing[] {
  const payload = record?.payload as { drawings?: TradingDrawing[] } | undefined;
  return Array.isArray(payload?.drawings)
    ? payload.drawings.filter((item) => item.instrumentId === instrumentId)
    : [];
}

async function loadEntry(entry: DrawingEntry): Promise<void> {
  if (entry.loaded) return;
  if (entry.loadPromise) return entry.loadPromise;
  entry.loadPromise = (async () => {
    entry.status = 'loading';
    emit(entry);
    try {
      const records = await tradingApi.documents('drawings');
      const record = records.find((item) => item.record_id === recordId(entry.instrumentId)) ?? null;
      entry.record = record;
      entry.state = replaceDrawings(drawingsFrom(record, entry.instrumentId));
      entry.serverState = null;
      entry.status = 'saved';
      entry.loaded = true;
    } catch {
      entry.status = 'error';
    } finally {
      entry.loadPromise = null;
      emit(entry);
    }
  })();
  return entry.loadPromise;
}

function payload(entry: DrawingEntry): Record<string, unknown> {
  return {
    instrumentId: entry.instrumentId,
    drawings: entry.state.drawings.map((drawing) => ({ ...drawing, selected: false })),
  };
}

async function saveEntry(entry: DrawingEntry): Promise<void> {
  try {
    const saved = entry.record
      ? await tradingApi.updateDocument('drawings', entry.record, payload(entry))
      : await tradingApi.createDocument('drawings', recordId(entry.instrumentId), payload(entry));
    entry.record = saved;
    entry.serverState = null;
    entry.status = 'saved';
    entry.loaded = true;
  } catch (error) {
    const conflict = error instanceof Error && error.message.includes('(409)');
    if (conflict) {
      const records = await tradingApi.documents('drawings').catch(() => []);
      const latest = records.find((item) => item.record_id === recordId(entry.instrumentId)) ?? null;
      entry.record = latest ?? entry.record;
      entry.serverState = latest ? replaceDrawings(drawingsFrom(latest, entry.instrumentId)) : emptyDrawingState();
      entry.status = 'conflict';
    } else {
      entry.status = 'error';
    }
  }
  emit(entry);
}

function persist(entry: DrawingEntry, next: DrawingState): void {
  entry.state = next;
  entry.status = 'saving';
  emit(entry);
  if (entry.timer) clearTimeout(entry.timer);
  entry.timer = setTimeout(() => {
    entry.timer = null;
    void saveEntry(entry);
  }, 450);
}

async function resolveConflict(entry: DrawingEntry, resolution: 'reload' | 'overwrite'): Promise<void> {
  if (entry.status !== 'conflict') return;
  if (resolution === 'reload') {
    entry.state = entry.serverState ?? emptyDrawingState();
    entry.serverState = null;
    entry.status = 'saved';
    entry.loaded = true;
    emit(entry);
    return;
  }
  entry.status = 'saving';
  emit(entry);
  await saveEntry(entry);
}

export function useTradingDrawings(instrumentId: string) {
  const entry = entryFor(instrumentId);
  const [current, setCurrent] = useState<DrawingSnapshot>(() => snapshot(entry));

  useEffect(() => {
    const update = () => setCurrent(snapshot(entry));
    entry.listeners.add(update);
    update();
    void loadEntry(entry);
    return () => {
      entry.listeners.delete(update);
    };
  }, [entry]);

  return {
    state: current.state,
    status: current.status,
    hasConflict: current.status === 'conflict',
    add: (drawing: TradingDrawing) => persist(entry, addDrawing(entry.state, drawing)),
    select: (id: string | null) => {
      entry.state = selectDrawing(entry.state, id);
      emit(entry);
    },
    movePoint: (id: string, index: number, point: DrawingPoint) => persist(entry, moveDrawingPoint(entry.state, id, index, point)),
    translate: (id: string, from: DrawingPoint, to: DrawingPoint) => persist(entry, translateDrawing(entry.state, id, from, to)),
    updateSelected: (patch: { style?: DrawingStyle; locked?: boolean; hidden?: boolean; text?: string }) => persist(entry, updateSelectedDrawing(entry.state, patch)),
    removeSelected: () => persist(entry, deleteSelectedDrawing(entry.state)),
    undo: () => persist(entry, undoDrawing(entry.state)),
    redo: () => persist(entry, redoDrawing(entry.state)),
    resolveConflict: (resolution: 'reload' | 'overwrite') => resolveConflict(entry, resolution),
  };
}
