import { describe, expect, it } from 'vitest';
import type { MarketBar } from '../tradingTypes';
import type { CoreIndicatorId, CoreIndicatorInstance } from './coreIndicators';
import { TradingIndicatorScheduler } from './indicatorScheduler';
import { fixture } from '../../../test/fixture';

function bars(count: number): MarketBar[] {
  return fixture(Array.from({ length: count }, (_, index) => ({
    instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
    interval: '1m',
    start_time: new Date(Date.UTC(2026, 0, 1, 0, index)).toISOString(),
    end_time: new Date(Date.UTC(2026, 0, 1, 0, index + 1)).toISOString(),
    open: String(100 + index),
    high: String(101 + index),
    low: String(99 + index),
    close: String(100 + index),
    volume: '10',
    is_final: true,
    adjustment_mode: 'raw',
    session: '24x7',
    provider: 'binance',
    ingestion_revision: 1,
    received_at: '2026-01-01T00:00:00Z',
  })));
}

describe('TradingIndicatorScheduler', () => {
  it('uses the deterministic fallback when Worker is unavailable', async () => {
    const scheduler = new TradingIndicatorScheduler(null);
    const outputs = await scheduler.calculate(bars(30), [{ id: 'sma', period: 20, enabled: true }]);
    expect(outputs?.[0].key).toBe('sma:20');
    expect(outputs?.[0].points).toHaveLength(11);
    scheduler.destroy();
  });

  it('suppresses stale calculations before they reach a chart', async () => {
    const scheduler = new TradingIndicatorScheduler(null);
    const first = scheduler.calculate(bars(30), [{ id: 'sma', period: 20, enabled: true }]);
    const second = scheduler.calculate(bars(30), [{ id: 'ema', period: 10, enabled: true }]);
    expect(await first).toBeNull();
    expect((await second)?.[0].key).toBe('ema:10');
    scheduler.destroy();
  });

  it('loads the compare symbol of a Correlation Coefficient on the chart interval', async () => {
    const calls: Array<[string, string, number]> = [];
    const scheduler = new TradingIndicatorScheduler(null, async (instrumentId, interval, limit) => {
      calls.push([instrumentId, interval, limit]);
      return bars(30);
    });
    const correlation: CoreIndicatorInstance = { id: 'tv-correlation-coefficient-cc' as CoreIndicatorId, period: 20, enabled: true, compareSymbol: 'equity:NASDAQ:QQQ' };
    const outputs = await scheduler.calculate(bars(30), [correlation, { id: 'sma', period: 20, enabled: true }]);
    expect(calls).toEqual([['equity:NASDAQ:QQQ', '1m', 100]]);
    expect(outputs?.map((output) => [output.key, output.points.length])).toEqual([['tv-correlation-coefficient-cc:cc', 11], ['sma:20', 11]]);
    // Cached for the next recalculation.
    await scheduler.calculate(bars(30), [correlation]);
    expect(calls).toHaveLength(1);
    scheduler.destroy();
  });

  it('plots nothing for a compare symbol whose bars fail to load', async () => {
    const scheduler = new TradingIndicatorScheduler(null, () => Promise.reject(new Error('offline')));
    const correlation: CoreIndicatorInstance = { id: 'tv-correlation-coefficient-cc' as CoreIndicatorId, period: 20, enabled: true, compareSymbol: 'equity:NASDAQ:QQQ' };
    const outputs = await scheduler.calculate(bars(30), [correlation]);
    expect(outputs?.[0].points).toEqual([]);
    scheduler.destroy();
  });

  it('returns no result after disposal', async () => {
    const scheduler = new TradingIndicatorScheduler(null);
    scheduler.destroy();
    expect(await scheduler.calculate(bars(30), [{ id: 'rsi', period: 14, enabled: true }])).toBeNull();
  });
});
