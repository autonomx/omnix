import { describe, expect, it } from 'vitest';
import { candlestickData, lineData, volumeData } from './chartAdapter';
import type { MarketBar } from '../tradingTypes';

const bar: MarketBar = {
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  interval: '1m',
  start_time: '2026-08-05T12:00:00+00:00',
  end_time: '2026-08-05T12:01:00+00:00',
  open: '100.25',
  high: '103.00',
  low: '99.50',
  close: '102.75',
  volume: '45.5',
  is_final: true,
  adjustment_mode: 'raw',
  session: '24x7',
  provider: 'binance',
  ingestion_revision: 1,
  received_at: '2026-08-05T12:01:00+00:00',
};

describe('Trading chart adapter normalization', () => {
  it('converts backend decimal strings at the chart boundary', () => {
    expect(candlestickData(bar)).toMatchObject({
      open: 100.25,
      high: 103,
      low: 99.5,
      close: 102.75,
    });
    expect(lineData(bar).value).toBe(102.75);
    expect(volumeData(bar).value).toBe(45.5);
  });

  it('uses epoch seconds and deterministic volume direction colors', () => {
    expect(candlestickData(bar).time).toBe(Date.parse(bar.start_time) / 1_000);
    expect(volumeData(bar).color).toContain('32,201,151');
    expect(volumeData({ ...bar, close: '99' }).color).toContain('255,107,107');
  });

  it('rejects invalid provider timestamps', () => {
    expect(() => candlestickData({ ...bar, start_time: 'not-a-date' })).toThrow(/Invalid Trading timestamp/);
  });
});
