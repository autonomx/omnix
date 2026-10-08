// The stored drawing document payload and its upgrades (TVP-0.4).
//
// Version 1 (no `schemaVersion`): drawings without `properties`; points could
// carry the pointer's x/y pixels next to time and price.
// Version 2: `schemaVersion: 2`; every drawing has its tool's properties
// (missing ones filled from defaults, stored ones kept as they are).
//
// Nothing stored is lost by loading and saving: entries this client can't
// read (bad points, another instrument) are kept verbatim and saved back, and
// a document from a newer schema is read-only.
import { normalizeDrawing, type DrawingPoint, type TradingDrawing } from './drawingCommands';

export const DRAWING_DOCUMENT_SCHEMA_VERSION = 2;

export type DrawingDocument = {
  /** The stored document's schema version (1 when it has none). */
  schemaVersion: number;
  instrumentId: string;
  /** Drawings this client loads and edits. */
  drawings: TradingDrawing[];
  /** Stored entries kept verbatim and saved back unchanged. */
  preserved: unknown[];
  /** Written by a newer schema: shown, never saved over. */
  readOnly: boolean;
};

export type DrawingDocumentPayload = {
  schemaVersion: typeof DRAWING_DOCUMENT_SCHEMA_VERSION;
  instrumentId: string;
  drawings: unknown[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function upgradePoint(value: unknown, version: number): DrawingPoint | null {
  if (!isRecord(value) || typeof value.time !== 'string' || !Number.isFinite(Date.parse(value.time))) return null;
  if (typeof value.price !== 'number' || !Number.isFinite(value.price)) return null;
  if (version >= 2) return { ...value } as DrawingPoint;
  // Version 1 leaked the pointer's pixel position into points; it was never data.
  const point: Record<string, unknown> = { ...value };
  delete point.x;
  delete point.y;
  return point as DrawingPoint;
}

function upgradeDrawing(value: unknown, version: number, instrumentId: string): TradingDrawing | null {
  if (!isRecord(value) || typeof value.drawingId !== 'string' || typeof value.toolType !== 'string') return null;
  if (value.instrumentId !== instrumentId || !Array.isArray(value.points) || value.points.length === 0) return null;
  const points = value.points.map((point) => upgradePoint(point, version));
  if (points.some((point) => point === null)) return null;
  return normalizeDrawing({ ...(value as unknown as TradingDrawing), points: points as DrawingPoint[], selected: false });
}

/** Reads any stored drawing payload. Entries it can't read are preserved, not dropped. */
export function upgradeDrawingDocument(payload: unknown, instrumentId: string): DrawingDocument {
  const record = isRecord(payload) ? payload : {};
  const version = typeof record.schemaVersion === 'number' ? record.schemaVersion : 1;
  const stored = Array.isArray(record.drawings) ? record.drawings : [];
  const drawings: TradingDrawing[] = [];
  const preserved: unknown[] = [];
  for (const entry of stored) {
    const drawing = upgradeDrawing(entry, version, instrumentId);
    if (drawing) drawings.push(drawing);
    else preserved.push(entry);
  }
  return {
    schemaVersion: version,
    instrumentId: typeof record.instrumentId === 'string' ? record.instrumentId : instrumentId,
    drawings,
    preserved,
    readOnly: version > DRAWING_DOCUMENT_SCHEMA_VERSION,
  };
}

/** The payload to save: the edited drawings plus every preserved entry, unchanged. */
export function drawingDocumentPayload(instrumentId: string, drawings: readonly TradingDrawing[], preserved: readonly unknown[] = []): DrawingDocumentPayload {
  return {
    schemaVersion: DRAWING_DOCUMENT_SCHEMA_VERSION,
    instrumentId,
    drawings: [...drawings.map((drawing) => ({ ...drawing, selected: false })), ...preserved],
  };
}
