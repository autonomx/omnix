import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const replayApi = vi.hoisted(() => ({
  advanceExecution: vi.fn(),
  placeExecutionOrder: vi.fn(),
}));

vi.mock('./tradingReplayApi', () => ({ tradingReplayApi: replayApi }));

import type { PaperAccountSnapshot } from './paperTypes';
import { barCloseTime, replayVisibleCount } from './replayClock';
import { replayAccountHasExposure, useTradingReplayStore } from './tradingReplayStore';
import type { MarketBar } from './tradingTypes';
import { useChartReplayClock } from './useTradingChartPanelReplayClock';
import { fixture } from '../../test/fixture';

const MINUTE = 60_000;
const BASE = Date.parse('2026-08-05T12:00:00Z');
const at = (minute: number) => BASE + minute * MINUTE;
const ROUND_TRIP_MS = 250;

function bar(index: number, low = 100): MarketBar {
  return fixture({
    instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
    interval: '1m',
    start_time: new Date(at(index)).toISOString(),
    end_time: new Date(at(index + 1)).toISOString(),
    open: '101', high: '102', low: String(low), close: '101', volume: '1',
    is_final: true, adjustment_mode: 'raw', session: '24x7', provider: 'binance',
    ingestion_revision: 1, received_at: new Date(at(index + 1)).toISOString(),
  });
}

type TestSnapshot = PaperAccountSnapshot & { advanced: number[] };

function account(openOrders: unknown[] = []): TestSnapshot {
  return fixture({
    account: { account_id: 'paper-1' },
    balances: [],
    positions: [],
    open_orders: openOrders,
    order_history: [],
    recent_fills: [],
    recent_ledger: [],
    advanced: [],
  });
}

/** A stand-in for the server kernel: a buy limit fills when a bar trades at or below it. */
async function slowKernel(snapshot: TestSnapshot, advanced: MarketBar): Promise<TestSnapshot> {
  await new Promise((resolve) => setTimeout(resolve, ROUND_TRIP_MS));
  const fills = snapshot.open_orders.filter((order) => Number(advanced.low) <= Number(order.limit_price));
  return {
    ...snapshot,
    advanced: [...snapshot.advanced, barCloseTime(advanced)],
    open_orders: snapshot.open_orders.filter((order) => !fills.includes(order)),
    positions: [...snapshot.positions, ...fills.map((order) => fixture<PaperAccountSnapshot['positions'][number]>({
      instrument_id: order.instrument_id, quantity: order.quantity, average_cost: order.limit_price,
    }))],
  };
}

const replay = () => useTradingReplayStore.getState();

function startPlayback(bars: MarketBar[], startIndex: number, seed: TestSnapshot) {
  const hook = renderHook(() => useChartReplayClock({
    active: true, replayMode: true, bars, chartKey: 'BTC||1m', reloadBars: () => undefined,
  }));
  act(() => {
    replay().chooseStart(barCloseTime(bars[startIndex]));
    replay().seedSnapshot(seed, 'test-session');
    replay().setSpeed(30);
    replay().setPlaying(true);
  });
  return hook;
}

describe('replay account execution queue', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    replay().clear();
    replayApi.advanceExecution.mockImplementation(slowKernel);
  });

  afterEach(() => {
    replay().clear();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('advances the account through every bar, in order, each on the previous result', async () => {
    const bars = Array.from({ length: 12 }, (_, index) => bar(index));
    const order = { order_id: 'limit-1', instrument_id: 'BTC', side: 'buy', order_type: 'limit', quantity: '1', limit_price: '50' };
    startPlayback(bars, 0, account([order]));

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });

    const calls = replayApi.advanceExecution.mock.calls as [TestSnapshot, MarketBar][];
    expect(calls.map(([, advanced]) => barCloseTime(advanced))).toEqual(bars.slice(1).map(barCloseTime));
    calls.forEach(([input], index) => {
      expect(input.advanced).toEqual(bars.slice(1, index + 1).map(barCloseTime));
    });
    expect((replay().snapshot as TestSnapshot).advanced).toHaveLength(11);
    expect(replay().advancedThrough).toBe(replay().clock);
  });

  it('fills a limit touched only by the middle bar of a three-bar tick', async () => {
    const bars = [bar(0), bar(1), bar(2), bar(3, 90), bar(4), bar(5)];
    const order = { order_id: 'limit-1', instrument_id: 'BTC', side: 'buy', order_type: 'limit', quantity: '1', limit_price: '95' };
    startPlayback(bars, 1, account([order]));

    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });

    const snapshot = replay().snapshot!;
    expect(snapshot.open_orders).toEqual([]);
    expect(snapshot.positions).toEqual([expect.objectContaining({ quantity: '1', average_cost: '95' })]);
  });

  it('never lets the clock run more than one tick ahead of the advanced account', async () => {
    const bars = Array.from({ length: 40 }, (_, index) => bar(index));
    const order = { order_id: 'limit-1', instrument_id: 'BTC', side: 'buy', order_type: 'limit', quantity: '1', limit_price: '1' };
    let maxLag = 0;
    const unsubscribe = useTradingReplayStore.subscribe((state) => {
      if (state.clock === null || state.advancedThrough === null || !replayAccountHasExposure(state.snapshot)) return;
      maxLag = Math.max(maxLag, replayVisibleCount(bars, state.clock) - replayVisibleCount(bars, state.advancedThrough));
    });
    startPlayback(bars, 0, account([order]));

    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    // 30× wants 30 bars a second, but the account takes 250 ms a bar.
    expect(replayVisibleCount(bars, replay().clock!)).toBeLessThan(10);
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    unsubscribe();

    expect(maxLag).toBeLessThanOrEqual(3);
    expect(replay().clock).toBe(barCloseTime(bars[39]));
    expect(replayApi.advanceExecution).toHaveBeenCalledTimes(39);
  });

  it('does not throttle playback when the account has nothing to fill', async () => {
    const bars = Array.from({ length: 60 }, (_, index) => bar(index));
    startPlayback(bars, 0, account());

    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });

    expect(replayVisibleCount(bars, replay().clock!)).toBe(31);
  });

  it('places replay orders after the queued bar advances', async () => {
    const bars = Array.from({ length: 5 }, (_, index) => bar(index));
    startPlayback(bars, 0, account());
    act(() => { replay().setPlaying(false); });
    replayApi.placeExecutionOrder.mockImplementation(async (snapshot: TestSnapshot) => ({
      snapshot: { ...snapshot, order_history: [{ order_id: 'market-1' }] },
      order: { order_id: 'market-1', status: 'filled' },
    }));

    act(() => { replay().stepForward(2); });
    act(() => { replay().setBar(bars[2]); });
    const placed = replay().placeOrder(fixture({ order_id: 'market-1' }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    await placed;

    const [orderSnapshot] = replayApi.placeExecutionOrder.mock.calls[0] as [TestSnapshot];
    expect(orderSnapshot.advanced).toEqual([barCloseTime(bars[1]), barCloseTime(bars[2])]);
    expect((replay().snapshot as TestSnapshot).advanced).toHaveLength(2);
    expect(replay().snapshot?.order_history).toHaveLength(1);
  });

  it('drops queued work when replay trading restarts', async () => {
    const bars = Array.from({ length: 5 }, (_, index) => bar(index));
    startPlayback(bars, 0, account());
    act(() => {
      replay().setPlaying(false);
      replay().stepForward(3);
      replay().resetToStart();
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });

    expect(replay().snapshot).toBeNull();
    expect(replay().pendingExecutions).toBe(0);
  });
});
