import { describe, expect, it } from 'vitest';
import fixture from './fixtures/coreIndicators.json';
import {
  CORE_INDICATOR_FORMULA_VERSION,
  exponentialMovingAverage,
  indicatorOutputs,
  relativeStrengthIndex,
  simpleMovingAverage,
} from './coreIndicators';
import type { MarketBar } from '../tradingTypes';

function close(actual: number[], expected: number[]) {
  expect(actual).toHaveLength(expected.length);
  actual.forEach((value, index) => expect(value).toBeCloseTo(expected[index], 10));
}

describe('versioned core indicators', () => {
  it('matches the shared SMA fixture', () => {
    expect(CORE_INDICATOR_FORMULA_VERSION).toBe(fixture.formulaVersion);
    close(simpleMovingAverage(fixture.closes, fixture.sma.period), fixture.sma.values);
  });

  it('matches the shared EMA fixture', () => {
    close(exponentialMovingAverage(fixture.closes, fixture.ema.period), fixture.ema.values);
  });

  it('matches Wilder RSI and documents warmup behavior', () => {
    close(relativeStrengthIndex(fixture.closes, fixture.rsi.period), fixture.rsi.values);
    expect(relativeStrengthIndex([1, 2, 3], 3)).toEqual([]);
  });

  it('fails closed for invalid periods', () => {
    expect(() => simpleMovingAverage([1], 0)).toThrow(/positive integer/);
    expect(() => exponentialMovingAverage([1], 1.5)).toThrow(/positive integer/);
  });

  it('calculates the linked community indicators with finite, aligned points', () => {
    const bars: MarketBar[] = Array.from({ length: 260 }, (_, index) => {
      const close = 100 + Math.sin(index / 5) * 8 + index * 0.05;
      return {
        instrument_id: 'fixture', interval: '1d',
        start_time: new Date(Date.UTC(2025, 0, index + 1)).toISOString(),
        end_time: new Date(Date.UTC(2025, 0, index + 2)).toISOString(),
        open: String(close - 0.5), high: String(close + 2), low: String(close - 2), close: String(close), volume: String(1_000 + index),
        is_final: true, adjustment_mode: 'raw', session: 'regular', provider: 'fixture', ingestion_revision: 1, received_at: new Date().toISOString(),
      };
    });
    const ids = [
      'bull-market-band', 'death-cross', 'ema-stack', 'fair-value-gap', 'golden-cross', 'ideal-bb',
      'log-macd', 'macd-dema', 'rsi-divergence', 'stochastic-rsi', 'swing-liquidity', 'volume-profile',
    ] as const;
    for (const id of ids) {
      const outputs = indicatorOutputs(bars, { id, period: id === 'volume-profile' ? 100 : 14, enabled: true });
      expect(outputs.every((output) => output.points.every((point) => Number.isFinite(point.value)))).toBe(true);
    }
  });
});
