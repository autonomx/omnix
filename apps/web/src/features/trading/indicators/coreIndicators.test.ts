import { describe, expect, it } from 'vitest';
import fixture from './fixtures/coreIndicators.json';
import {
  CORE_INDICATOR_FORMULA_VERSION,
  exponentialMovingAverage,
  relativeStrengthIndex,
  simpleMovingAverage,
} from './coreIndicators';

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
});
