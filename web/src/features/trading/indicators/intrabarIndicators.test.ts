import { afterEach, describe, expect, it, vi } from 'vitest';
import { fixture } from '../../../test/fixture';
import { clearIntrabarCache } from '../intrabarData';
import { tradingApi } from '../tradingApi';
import type { MarketBar } from '../tradingTypes';
import type { CoreIndicatorInstance } from './coreIndicators';
import { TradingIndicatorScheduler } from './indicatorScheduler';
import {
  calculateIntrabarIndicatorOutputs, cumulativeVolumeDeltaPoints, intrabarDeltas, intrabarLowerInterval, volumeDeltaPoints,
} from './intrabarIndicators';
import { tradingViewBuiltInInputs, tradingViewBuiltInPlotDefinitions } from './tradingViewBuiltIns';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const T0 = Date.UTC(2026, 7, 13, 22);

function bar(start: number, minutes: number, open: number, close: number, volume: number, interval: string): MarketBar {
  return fixture({
    instrument_id: 'crypto:BINANCE:spot:BTC-USDT', interval, start_time: new Date(start).toISOString(), end_time: new Date(start + minutes * MINUTE).toISOString(),
    open: String(open), high: String(Math.max(open, close) + 1), low: String(Math.min(open, close) - 1), close: String(close), volume: String(volume),
    is_final: true, adjustment_mode: 'raw', session: '24x7', provider: 'binance', ingestion_revision: 1, received_at: new Date(start + minutes * MINUTE).toISOString(),
  });
}

// Hours 22:00 and 23:00 on one UTC day, 00:00 on the next; four 15m bars each.
const hours = [0, 1, 2].map((i) => bar(T0 + i * HOUR, 60, 100, 101, 0, '1h'));
const quarters = [
  // 22:00: up 10, down 4, unchanged above the previous close (up) 3, unchanged at it (keeps up) 2 -> 11, max 11, min 0.
  [100, 101, 10], [101, 100, 4], [101, 101, 3], [101, 101, 2],
  // 23:00: down 5, down 5, up 1, unchanged below the previous close (down) 2 -> -11, min -11.
  [101, 100, 5], [100, 99, 5], [99, 100, 1], [99.5, 99.5, 2],
  // 00:00: up 6 each.
  [99, 100, 6], [100, 101, 6], [101, 102, 6], [102, 103, 6],
].map(([open, close, volume], i) => bar(T0 + i * 15 * MINUTE, 15, open, close, volume, '15m'));

afterEach(() => {
  clearIntrabarCache();
  vi.restoreAllMocks();
});

describe('volume delta (TVP-6.4)', () => {
  it('counts each lower bar as buying or selling by its close', () => {
    const deltas = intrabarDeltas(hours, quarters, '1h');
    expect(deltas.get(T0)).toEqual({ delta: 11, max: 11, min: 0 });
    expect(deltas.get(T0 + HOUR)).toEqual({ delta: -11, max: 0, min: -11 });
    expect(deltas.get(T0 + 2 * HOUR)?.delta).toBe(24);
    expect(volumeDeltaPoints(hours, deltas).map((point) => [point.value, point.color])).toEqual([[11, '#089981'], [-11, '#f23645'], [24, '#089981']]);
  });

  it('adds the deltas up within each anchor period', () => {
    const deltas = intrabarDeltas(hours, quarters, '1h');
    expect(cumulativeVolumeDeltaPoints(hours, deltas, 'D').map((point) => point.value)).toEqual([11, 0, 24]);
    expect(cumulativeVolumeDeltaPoints(hours, deltas, 'M').map((point) => point.value)).toEqual([11, 0, 24]);
    // Chart bars without lower bars have no value.
    expect(volumeDeltaPoints([...hours, bar(T0 + 3 * HOUR, 60, 1, 1, 0, '1h')], deltas)).toHaveLength(3);
  });

  it('reads the chosen intrabar timeframe when it fits the chart, else auto', () => {
    const instance = (params?: Record<string, string>) => ({ id: 'tv-volume-delta', period: 1, enabled: true, params }) as unknown as CoreIndicatorInstance;
    expect(intrabarLowerInterval(instance(), '1h')).toBe('1m');
    expect(intrabarLowerInterval(instance({ lowerInterval: '15m' }), '1h')).toBe('15m');
    expect(intrabarLowerInterval(instance({ lowerInterval: '4h' }), '1h')).toBe('1m');
    expect(tradingViewBuiltInInputs('tv-cumulative-volume-delta')?.params.map((param) => param.key)).toEqual(['anchor', 'lowerInterval']);
    expect(tradingViewBuiltInPlotDefinitions({ id: 'tv-volume-delta', period: 1 })).toEqual([{ key: 'tv-volume-delta:delta', title: 'Volume Delta' }]);
  });

  it('loads the lower bars on the chart feed and draws a histogram in its own pane', async () => {
    const spy = vi.spyOn(tradingApi, 'intrabars').mockResolvedValue({ bars: quarters, complete: true } as never);
    const indicator = { id: 'tv-cumulative-volume-delta', period: 1, enabled: true, params: { lowerInterval: '15m' } } as unknown as CoreIndicatorInstance;
    const [output] = await calculateIntrabarIndicatorOutputs(hours, indicator, { bindingId: 'binance:spot' });
    expect(output).toMatchObject({ key: 'tv-cumulative-volume-delta:cvd', title: 'CVD (15m)', pane: 1, kind: 'histogram' });
    expect(output.points.map((point) => point.value)).toEqual([11, 0, 24]);
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ bindingId: 'binance:spot', interval: '1h', lowerInterval: '15m', start: T0, end: T0 + 3 * HOUR }));
  });

  it('draws nothing when the lower bars fail to load', async () => {
    vi.spyOn(tradingApi, 'intrabars').mockRejectedValue(new Error('down'));
    const indicator = { id: 'tv-volume-delta', period: 1, enabled: true } as unknown as CoreIndicatorInstance;
    expect(await calculateIntrabarIndicatorOutputs(hours, indicator)).toEqual([]);
  });

  it('is computed by the indicator scheduler off the worker, with the chart feed', async () => {
    const spy = vi.spyOn(tradingApi, 'intrabars').mockResolvedValue({ bars: quarters, complete: true } as never);
    const scheduler = new TradingIndicatorScheduler(null);
    const outputs = await scheduler.calculate(hours, [{ id: 'tv-volume-delta', period: 1, enabled: true, params: { lowerInterval: '15m' } } as unknown as CoreIndicatorInstance], { bindingId: 'feed' });
    expect(outputs?.map((output) => output.key)).toEqual(['tv-volume-delta:delta']);
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ bindingId: 'feed' }));
    scheduler.destroy();
  });
});
