import { describe, expect, it } from 'vitest';
import type { PaperAccountSnapshot } from './paperTypes';
import { advanceReplaySnapshot, createReplaySnapshot, placeReplayOrder } from './replayTrading';
import type { MarketBar } from './tradingTypes';

const bar = (close: string, high = close, low = close): MarketBar => ({
  start_time: '2024-01-02T10:00:00Z',
  end_time: '2024-01-02T11:00:00Z',
  open: close,
  high,
  low,
  close,
  volume: '100',
  is_final: true,
  adjustment_mode: 'raw',
  session: '24x7',
  provider: 'replay-test',
  provider_event_id: null,
  provider_sequence: null,
  ingestion_revision: 1,
  received_at: '2024-01-02T11:00:01Z',
} as MarketBar);

const snapshot = (): PaperAccountSnapshot => ({
  account: {
    account_id: 'paper-1', name: 'Paper', base_currency: 'USD', commission_bps: '0',
    enabled: true, revision: 1,
  },
  balances: [{ currency: 'USD', available: '1000', reserved: '25' }],
  positions: [],
  open_orders: [],
  order_history: [{
    account_id: 'paper-1', order_id: 'actual-order', instrument_id: 'equity:NYSE:TEST',
    side: 'buy', order_type: 'market', quantity: '1', status: 'filled', filled_quantity: '1',
    idempotency_key: 'actual-order',
  }],
  recent_fills: [],
  recent_ledger: [],
});

describe('replay trading', () => {
  it('detaches replay cash and history from the paper account snapshot', () => {
    const source = snapshot();
    const replay = createReplaySnapshot(source);

    expect(replay.balances[0]).toMatchObject({ available: '1025', reserved: '0' });
    expect(replay.order_history).toEqual([]);
    expect(source.order_history).toHaveLength(1);
  });

  it('fills market orders at the current replay bar and leaves the source unchanged', () => {
    const source = createReplaySnapshot(snapshot());
    const result = placeReplayOrder(source, {
      order_id: 'replay-order-1', instrument_id: 'equity:NYSE:TEST', binding_id: null,
      side: 'buy', order_type: 'market', quantity: '2', limit_price: null, stop_price: null,
      reference_price: '101', idempotency_key: 'replay-order-1',
    }, bar('101'));

    expect(result.order).toMatchObject({ status: 'filled', average_fill_price: '101', filled_quantity: '2' });
    expect(result.snapshot.positions[0]).toMatchObject({ quantity: '2', average_cost: '101' });
    expect(result.snapshot.order_history).toHaveLength(1);
    expect(source.order_history).toEqual([]);
  });

  it('holds a limit order until a later replay candle reaches it', () => {
    const source = createReplaySnapshot(snapshot());
    const placed = placeReplayOrder(source, {
      order_id: 'replay-order-2', instrument_id: 'equity:NYSE:TEST', binding_id: null,
      side: 'buy', order_type: 'limit', quantity: '2', limit_price: '90', stop_price: null,
      reference_price: null, idempotency_key: 'replay-order-2',
    }, bar('100'));

    expect(placed.order.status).toBe('open');
    expect(placed.snapshot.open_orders).toHaveLength(1);
    const advanced = advanceReplaySnapshot(placed.snapshot, bar('92', '95', '89'));
    expect(advanced.open_orders).toEqual([]);
    expect(advanced.order_history?.[0]).toMatchObject({ status: 'filled', average_fill_price: '90' });
  });
});
