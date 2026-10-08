import { describe, expect, it } from 'vitest';
import { DRAWING_DOCUMENT_SCHEMA_VERSION, drawingDocumentPayload, upgradeDrawingDocument } from './drawingDocument';
import v1Payload from './fixtures/drawing-document-v1.json';

const instrumentId = 'crypto:BINANCE:spot:BTC-USDT';

describe('drawing document upgrade', () => {
  it('upgrades a version 1 payload: properties filled, pixel coordinates dropped', () => {
    const upgraded = upgradeDrawingDocument(v1Payload, instrumentId);
    expect(upgraded.schemaVersion).toBe(2);
    expect(upgraded.instrumentId).toBe(instrumentId);
    expect(upgraded.drawings.map((drawing) => drawing.toolType)).toEqual(['trend-line', 'fibonacci', 'text']);
    const [trend, fibonacci, text] = upgraded.drawings;
    expect(trend.points).toEqual([
      { time: '2026-10-06T13:00:00.000Z', price: 62114.25 },
      { time: '2026-10-07T09:00:00.000Z', price: 63980.5 },
    ]);
    expect(trend.properties).toEqual({ extendLeft: false, extendRight: false });
    expect(fibonacci.properties).toEqual({ levels: [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1], showLabels: true, extendLeft: false, extendRight: false });
    expect(fibonacci).toMatchObject({ revision: 1, locked: true, style: { color: '#ffd43b', lineWidth: 1, lineStyle: 'dashed' } });
    expect(text).toMatchObject({ hidden: true, text: 'Breakout retest', properties: {} });
  });

  it('round-trips the current version unchanged', () => {
    const upgraded = upgradeDrawingDocument(v1Payload, instrumentId);
    const saved = JSON.parse(JSON.stringify(drawingDocumentPayload(instrumentId, upgraded.drawings)));
    expect(saved.schemaVersion).toBe(DRAWING_DOCUMENT_SCHEMA_VERSION);
    expect(upgradeDrawingDocument(saved, instrumentId)).toEqual(upgraded);
  });

  it('keeps newer properties and drops drawings it cannot read', () => {
    const upgraded = upgradeDrawingDocument({
      schemaVersion: 2,
      drawings: [
        { drawingId: 'a', instrumentId, toolType: 'trend-line', points: [{ time: '2026-10-07T00:00:00.000Z', price: 1 }], selected: true, revision: 1, properties: { extendRight: true, label: 'kept' } },
        { drawingId: 'b', instrumentId, toolType: 'trend-line', points: [{ time: 7, price: 1 }], selected: false, revision: 1 },
        { drawingId: 'c', instrumentId, toolType: 'trend-line', selected: false, revision: 1 },
      ],
    }, instrumentId);
    expect(upgraded.drawings).toHaveLength(1);
    expect(upgraded.drawings[0]).toMatchObject({ selected: false, properties: { extendLeft: false, extendRight: true, label: 'kept' } });
    expect(upgradeDrawingDocument(null, instrumentId)).toEqual({ schemaVersion: 2, instrumentId, drawings: [] });
  });
});
