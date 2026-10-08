import { describe, expect, it } from 'vitest';
import { candlestickData, constrainZoomOutRange, DrawingTimeIndex, drawingLogicalIndexForTime, drawingTimeForLogicalIndex, heikinAshiBars, lineData, normalizeChartBars, upsertChartBar, renkoBars, TRADING_CHART_TYPE_OPTIONS, volumeData } from './chartAdapter';
import type { MarketBar } from '../tradingTypes';
import { fixture } from '../../../test/fixture';

const bar: MarketBar = fixture({
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
});
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
  it('merges equivalent ISO timestamps without duplicating indicator or replay bars', () => {
    const update = { ...bar, start_time: '2026-08-05T12:00:00.000Z', close: '104', ingestion_revision: 2 };
    const source = [bar, secondBar];
    const result = upsertChartBar(source, update);
    expect(result).toEqual([update, secondBar]);
    expect(source).toEqual([bar, secondBar]);
    expect(upsertChartBar(result, bar)).toEqual(result);
  });

  it('inserts an out-of-order stream bar in time order', () => {
    expect(upsertChartBar([secondBar], bar)).toEqual([bar, secondBar]);
    expect(upsertChartBar([], bar)).toEqual([bar]);
  });

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

  it('normalizes chart bars to strictly increasing epoch seconds', () => {
    const corrected = {
      ...secondBar,
      start_time: '2026-08-05T12:01:00.500+00:00',
      close: '15',
      ingestion_revision: 2,
    };
    const normalized = normalizeChartBars([corrected, { ...bar, start_time: 'not-a-date' }, bar, secondBar]);

    expect(normalized).toHaveLength(2);
    expect(normalized[0]).toBe(bar);
    expect(normalized[1]).toBe(corrected);
    expect(Math.floor(Date.parse(normalized[1].start_time) / 1_000)).toBe(
      Math.floor(Date.parse(secondBar.start_time) / 1_000),
    );
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

  it('indexes bar times once for repeated drawing projections', () => {
    const thirdBar = { ...bar, start_time: '2026-08-05T12:02:00+00:00' };
    const index = new DrawingTimeIndex([bar, secondBar, thirdBar]);
    expect(index.logicalIndexForTime('2026-08-05T12:01:00.000Z')).toBe(1);
    expect(index.logicalIndexForTime('2026-08-05T12:02:00.000Z')).toBe(2);
    // Between bars a time interpolates; past the last bar it extrapolates at the bar interval.
    expect(index.logicalIndexForTime('2026-08-05T12:00:30.000Z')).toBe(0.5);
    expect(index.logicalIndexForTime('2026-08-05T12:05:00.000Z')).toBe(5);
    expect(index.logicalIndexForTime('2026-08-05T11:58:00.000Z')).toBe(-2);
    expect(index.logicalIndexForTime('not-a-date')).toBeNull();
    expect(index.timeForLogicalIndex(1)).toBe(secondBar.start_time);
    expect(index.timeForLogicalIndex(1.2)).toBe('2026-08-05T12:01:12.000Z');
    expect(index.timeForLogicalIndex(6)).toBe('2026-08-05T12:06:00.000Z');
    expect(index.timeAfterBars('2026-08-05T12:01:00.000Z', 3)).toBe('2026-08-05T12:04:00.000Z');
    expect(new DrawingTimeIndex([]).logicalIndexForTime('2026-08-05T12:00:00.000Z')).toBeNull();
  });

  describe('drawing times on gapped data', () => {
    // Two 5m sessions, 13:30-19:55 UTC, with an overnight gap between them.
    const sessions = ['2026-10-05', '2026-10-06'].flatMap((day) => Array.from({ length: 78 }, (_, minute) => ({
      ...bar,
      start_time: new Date(Date.parse(`${day}T13:30:00.000Z`) + minute * 300_000).toISOString(),
    })));
    const index = new DrawingTimeIndex(sessions);

    it('maps a time inside a later session to its own bars, not by the first bar and the interval', () => {
      expect(index.logicalIndexForTime('2026-10-06T13:32:00.000Z')).toBeCloseTo(78.4, 9);
      expect(index.logicalIndexForTime('2026-10-06T19:55:00.000Z')).toBe(155);
    });

    it('extrapolates past the last bar from that bar', () => {
      expect(index.logicalIndexForTime('2026-10-06T20:05:00.000Z')).toBe(157);
      expect(index.timeForLogicalIndex(157)).toBe('2026-10-06T20:05:00.000Z');
      expect(index.timeForLogicalIndex(-1)).toBe('2026-10-05T13:25:00.000Z');
    });

    it('is the exact inverse of timeForLogicalIndex', () => {
      for (let logical = -20; logical <= 180; logical += 0.37) {
        const time = index.timeForLogicalIndex(logical)!;
        expect(index.logicalIndexForTime(time)).toBeCloseTo(logical, 5);
        expect(index.timeForLogicalIndex(index.logicalIndexForTime(time)!)).toBe(time);
      }
    });

    it('places drawings made on another interval between the bars they fall in', () => {
      // A 1m anchor on a 5m chart.
      expect(index.logicalIndexForTime('2026-10-05T13:41:00.000Z')).toBeCloseTo(2.2, 9);
      // A 1h anchor on a 1D chart, over a weekend.
      const daily = ['2026-10-02', '2026-10-05', '2026-10-06'].map((day) => ({ ...bar, start_time: `${day}T00:00:00.000Z` }));
      const days = new DrawingTimeIndex(daily);
      expect(days.logicalIndexForTime('2026-10-05T15:00:00.000Z')).toBeCloseTo(1 + 15 / 24, 9);
      expect(days.logicalIndexForTime('2026-10-07T12:00:00.000Z')).toBeCloseTo(2.5, 9);
    });
  });
});
