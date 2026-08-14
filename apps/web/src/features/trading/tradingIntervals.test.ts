import { describe, expect, it } from 'vitest';
import {
  intervalCompactLabel,
  intervalMenuLabel,
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
});
