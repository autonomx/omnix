import { describe, expect, it } from 'vitest';
import type { MarketBar } from './tradingTypes';
import { percentChangeFromBars, percentChangeFromLookback } from './tradingWatchlistChange';

function bar(
  close: string,
  startTime = '2026-07-01T00:00:00Z',
  open = close,
): MarketBar {
  return {
    instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
    interval: '1d',
    start_time: startTime,
    end_time: '2026-08-01T00:00:00Z',
    open,
    high: close,
    low: close,
    close,
    volume: '0',
    is_final: true,
    adjustment_mode: 'raw',
    session: '24x7',
    provider: 'binance',
    provider_event_id: null,
    provider_sequence: null,
    ingestion_revision: 1,
    received_at: '2026-08-15T00:00:00Z',
  };
}

describe('percentChangeFromBars', () => {
  it('calculates change from the current interval open to the current price', () => {
    expect(percentChangeFromBars('115', [bar('100'), bar('110', '2026-08-01T00:00:00Z', '100')])).toBeCloseTo(15);
  });

  it('uses the latest candle close when a live quote is unavailable', () => {
    expect(percentChangeFromBars(null, [bar('100'), bar('110', '2026-08-01T00:00:00Z', '100')])).toBeCloseTo(10);
  });

  it('returns null when the current interval has no usable open', () => {
    expect(percentChangeFromBars('115', [bar('110', '2026-08-01T00:00:00Z', '0')])).toBeNull();
  });

  it('derives a missing interval from smaller candles', () => {
    expect(percentChangeFromLookback(
      '115',
      [bar('100', '2026-07-01T00:00:00Z'), bar('110', '2026-08-01T00:00:00Z', '100')],
      '1mo',
    )).toBeCloseTo(15);
  });
});
