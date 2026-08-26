import { describe, expect, it } from 'vitest';
import {
  dateInputValue,
  formatTradingTime,
  formatTradingTimezoneOffset,
  tradingDateRangeWithinLoadedHistory,
  TRADING_TIMEZONE_OPTIONS,
  zonedDateTimeToUtc,
} from './tradingTime';

describe('TradingView-style timezone formatting', () => {
  const sample = '2026-08-25T04:16:00.000Z';

  it('formats UTC-7 as a local 12-hour clock time', () => {
    expect(formatTradingTime(sample, 'America/Vancouver')).toBe('9:16:00 PM');
    expect(formatTradingTimezoneOffset(sample, 'America/Vancouver')).toBe('UTC-7');
  });

  it('converts a selected timezone date range to UTC boundaries', () => {
    expect(zonedDateTimeToUtc('2026-08-25', 'America/Vancouver')).toBe(Date.parse('2026-08-25T07:00:00.000Z'));
    expect(zonedDateTimeToUtc('2026-08-25', 'America/Vancouver', true)).toBe(Date.parse('2026-08-26T06:59:59.999Z'));
  });

  it('uses the selected timezone when seeding custom range inputs', () => {
    expect(dateInputValue(sample, 'America/Vancouver')).toBe('2026-08-24');
  });

  it('derives DST-sensitive offsets at render time instead of hard-coding them in labels', () => {
    expect(formatTradingTimezoneOffset('2026-01-15T20:00:00.000Z', 'America/Vancouver')).toBe('UTC-8');
    expect(formatTradingTimezoneOffset(sample, 'America/Vancouver')).toBe('UTC-7');
    expect(TRADING_TIMEZONE_OPTIONS.find((option) => option.id === 'vancouver')?.label).toBe('Vancouver');
  });

  it('rejects custom ranges outside the dates that are actually loaded', () => {
    expect(tradingDateRangeWithinLoadedHistory(
      '2026-08-20',
      '2026-08-25',
      '2026-08-20T13:30:00.000Z',
      '2026-08-25T20:00:00.000Z',
      'America/New_York',
    )).toBe(true);
    expect(tradingDateRangeWithinLoadedHistory(
      '2026-08-01',
      '2026-08-25',
      '2026-08-20T13:30:00.000Z',
      '2026-08-25T20:00:00.000Z',
      'America/New_York',
    )).toBe(false);
  });
});
