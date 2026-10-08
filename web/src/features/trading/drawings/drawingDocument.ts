// The stored drawing document payload and its upgrades (TVP-0.4).
//
// Version 1 (no `schemaVersion`): drawings without `properties`; points could
// carry the pointer's x/y pixels next to time and price.
// Version 2: `schemaVersion: 2`; points hold time and price only, and every
// drawing has its tool's properties with defaults filled in.
import { normalizeDrawing, type DrawingPoint, type TradingDrawing } from './drawingCommands';

export const DRAWING_DOCUMENT_SCHEMA_VERSION = 2;

export type DrawingDocumentPayload = {
  schemaVersion: typeof DRAWING_DOCUMENT_SCHEMA_VERSION;
  instrumentId: string;
  drawings: TradingDrawing[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function upgradePoint(value: unknown): DrawingPoint | null {
  if (!isRecord(value) || typeof value.time !== 'string' || typeof value.price !== 'number') return null;
  return { time: value.time, price: value.price };
}

function upgradeDrawing(value: unknown): TradingDrawing | null {
  if (!isRecord(value) || typeof value.drawingId !== 'string' || typeof value.toolType !== 'string' || !Array.isArray(value.points)) return null;
  const points = value.points.map(upgradePoint);
  if (points.some((point) => point === null)) return null;
  return normalizeDrawing({ ...(value as unknown as TradingDrawing), points: points as DrawingPoint[], selected: false });
}

/** Reads any stored drawing payload as the current version. Unreadable drawings are dropped. */
export function upgradeDrawingDocument(payload: unknown, instrumentId: string): DrawingDocumentPayload {
  const record = isRecord(payload) ? payload : {};
  const drawings = Array.isArray(record.drawings) ? record.drawings : [];
  return {
    schemaVersion: DRAWING_DOCUMENT_SCHEMA_VERSION,
    instrumentId: typeof record.instrumentId === 'string' ? record.instrumentId : instrumentId,
    drawings: drawings
      .map(upgradeDrawing)
      .filter((drawing): drawing is TradingDrawing => drawing !== null && drawing.instrumentId === instrumentId),
  };
}

export function drawingDocumentPayload(instrumentId: string, drawings: readonly TradingDrawing[]): DrawingDocumentPayload {
  return {
    schemaVersion: DRAWING_DOCUMENT_SCHEMA_VERSION,
    instrumentId,
    drawings: drawings.map((drawing) => ({ ...drawing, selected: false })),
  };
}
