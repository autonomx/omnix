import { beforeEach, describe, expect, it, vi } from 'vitest';
import { tradingDrawingRecordId } from '../drawings/useTradingDrawings';
import { tradingApi } from '../tradingApi';
import type { TradingDocument } from '../tradingTypes';
import { copyWorkspaceDrawings, workspaceDrawingCopies } from './duplicateWorkspace';

function drawingRecord(workspaceId: string, tabId: string, instrumentId: string, status = 'active', drawings: unknown[] = [{ drawingId: 'd1', instrumentId }]): TradingDocument {
  return {
    record_id: tradingDrawingRecordId(instrumentId, `${workspaceId}:${tabId}`),
    record_type: 'drawing',
    payload: { instrumentId, drawings },
    revision: 3,
    status,
    updated_at: '2026-10-08T00:00:00Z',
  } as TradingDocument;
}

describe('duplicate layout drawings (TVP-2.5)', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('maps each tab drawing document of the source workspace to the duplicate', () => {
    const records = [
      drawingRecord('main', 'tab-1', 'crypto:BINANCE:spot:BTC-USDT'),
      drawingRecord('main', 'tab-2', 'equity:NASDAQ:AAPL'),
      drawingRecord('main', 'tab-1', 'crypto:BINANCE:spot:ETH-USDT', 'archived'),
      drawingRecord('main', 'tab-1', 'crypto:BINANCE:spot:SOL-USDT', 'active', []),
      // A workspace whose id starts with the source id must not be copied.
      drawingRecord('main-copy-1234abcd', 'tab-1', 'crypto:BINANCE:spot:BTC-USDT'),
      drawingRecord('other', 'tab-1', 'crypto:BINANCE:spot:BTC-USDT'),
    ];
    const copies = workspaceDrawingCopies(records, 'main', 'main-copy-9999', ['tab-1', 'tab-2']);
    expect(copies.map((copy) => copy.recordId)).toEqual([
      tradingDrawingRecordId('crypto:BINANCE:spot:BTC-USDT', 'main-copy-9999:tab-1'),
      tradingDrawingRecordId('equity:NASDAQ:AAPL', 'main-copy-9999:tab-2'),
    ]);
    expect(copies[0].payload).toEqual(records[0].payload);
    expect(copies[0].payload).not.toBe(records[0].payload);
  });

  it('creates the copies through the drawing documents API and skips ones that exist', async () => {
    const source = drawingRecord('main', 'tab-1', 'crypto:BINANCE:spot:BTC-USDT');
    const existing = drawingRecord('copy', 'tab-1', 'equity:NASDAQ:AAPL');
    const alsoSource = drawingRecord('main', 'tab-1', 'equity:NASDAQ:AAPL');
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([source, existing, alsoSource]);
    const create = vi.spyOn(tradingApi, 'createDocument').mockImplementation(async (_kind, recordId, payload) => ({ ...source, record_id: recordId, payload }));
    await expect(copyWorkspaceDrawings('main', 'copy', ['tab-1'])).resolves.toBe(1);
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith('drawings', tradingDrawingRecordId('crypto:BINANCE:spot:BTC-USDT', 'copy:tab-1'), source.payload);
  });
});
