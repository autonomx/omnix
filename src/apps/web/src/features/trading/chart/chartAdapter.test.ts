import { describe, expect, it } from 'vitest';
import { candlestickData, constrainZoomOutRange, drawingLogicalIndexForTime, drawingTimeForLogicalIndex, heikinAshiBars, lineData, renkoBars, TRADING_CHART_TYPE_OPTIONS, volumeData } from './chartAdapter';
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
const secondBar: MarketBar = {
  ...bar,
  start_time: '2026-08-05T12:01:00+00:00',
  end_time: '2026-08-05T12:02:00+00:00',
  open: '12',
  high: '16',
  low: '10',
  close: '14',
};

describe('Trading chart adapter normalization', () => {
  it('exposes the complete TradingView-style chart type catalog', () => {
    expect(TRADING_CHART_TYPE_OPTIONS.map((option) => option.label)).toEqual([
      'Bars', 'Candles', 'Hollow candles', 'Volume candles', 'Line', 'Line with markers', 'Step line',
      'Area', 'HLC area', 'Baseline', 'Columns', 'High-low', 'Volume footprint', 'Time price opportunity',
      'Session volume profile', 'Heikin Ashi', 'Renko', 'Line break', 'Kagi', 'Point & figure', 'Range',
    ]);
  });

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

  it('applies a selected display-currency multiplier to price data', () => {
    const converted = candlestickData(bar, 1.4);
    expect(converted.open).toBeCloseTo(140.35);
    expect(converted.high).toBeCloseTo(144.2);
    expect(converted.low).toBeCloseTo(139.3);
    expect(converted.close).toBeCloseTo(143.85);
    expect(lineData(bar, 1.4).value).toBeCloseTo(143.85);
  });

  it('builds standard Heikin Ashi candles from the source bars', () => {
    const [first, second] = heikinAshiBars([{ ...bar, open: '10', high: '14', low: '8', close: '12' }, secondBar]);
    expect(first).toMatchObject({ open: '11', high: '14', low: '8', close: '11' });
    expect(second).toMatchObject({ open: '11', high: '16', low: '10', close: '13' });
  });

  it('creates ordered synthetic Renko bars without duplicate chart timestamps', () => {
    const derived = renkoBars([
      { ...bar, close: '100', high: '101', low: '99' },
      { ...secondBar, close: '106', high: '107', low: '99' },
    ]);
    expect(derived.length).toBeGreaterThan(0);
    expect(new Set(derived.map((item) => item.start_time)).size).toBe(derived.length);
    expect(derived.every((item) => Number(item.high) >= Number(item.open) && Number(item.high) >= Number(item.close))).toBe(true);
    expect(derived.every((item) => Number(item.low) <= Number(item.open) && Number(item.low) <= Number(item.close))).toBe(true);
  });

  it('uses epoch seconds and deterministic volume direction colors', () => {
    expect(candlestickData(bar).time).toBe(Date.parse(bar.start_time) / 1_000);
    expect(volumeData(bar).color).toContain('32,201,151');
    expect(volumeData({ ...bar, close: '99' }).color).toContain('255,107,107');
  });

  it('rejects invalid provider timestamps', () => {
    expect(() => candlestickData({ ...bar, start_time: 'not-a-date' })).toThrow(/Invalid Trading timestamp/);
  });

  it('caps zoom width without pulling a panned chart back over the data', () => {
    expect(constrainZoomOutRange({ from: 130, to: 330 }, { from: 0, to: 100 }, 230)).toEqual({ from: 180, to: 280 });
    expect(constrainZoomOutRange({ from: -330, to: -130 }, { from: 0, to: 100 }, -230)).toEqual({ from: -280, to: -180 });
  });

  it('extrapolates drawing timestamps beyond the loaded bar range', () => {
    const bars = [bar, secondBar];
    expect(drawingTimeForLogicalIndex(2, bars)).toBe('2026-08-05T12:02:00.000Z');
    expect(drawingLogicalIndexForTime('2026-08-05T12:03:00.000Z', bars)).toBe(3);
  });
});
