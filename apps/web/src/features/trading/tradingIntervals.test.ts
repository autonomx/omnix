import { describe, expect, it } from 'vitest';
import {
  aggregationBaseInterval,
  intervalCompactLabel,
  intervalMenuLabel,
  isIntervalAvailable,
  TRADING_VIEW_INTERVAL_GROUPS,
} from './tradingIntervals';

describe('TradingView interval catalog', () => {
  it('includes every displayed interval category', () => {
    expect(TRADING_VIEW_INTERVAL_GROUPS.map((group) => group.label)).toEqual([
      'Ticks',
      'Seconds',
      'Minutes',
      'Hours',
      'Days',
      'Weeks',
      'Months',
      'Ranges',
    ]);
    expect(TRADING_VIEW_INTERVAL_GROUPS.flatMap((group) => group.options)).toHaveLength(47);
  });

  it('keeps compact toolbar labels distinct from menu labels', () => {
    expect(intervalMenuLabel('1m')).toBe('1 minute');
    expect(intervalMenuLabel('1mo')).toBe('1 month');
    expect(intervalCompactLabel('1m')).toBe('1m');
    expect(intervalCompactLabel('1mo')).toBe('1M');
  });

  it('marks intervals derivable from a supported base as available', () => {
    const supported = ['1m', '5m', '15m', '1h', '1d'];
    expect(aggregationBaseInterval('2h', supported)).toBe('1h');
    expect(aggregationBaseInterval('30m', supported)).toBe('15m');
    expect(isIntervalAvailable('2d', supported)).toBe(true);
    expect(isIntervalAvailable('1s', supported)).toBe(false);
  });
});
