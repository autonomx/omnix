import { describe, expect, it } from 'vitest';
import {
  dateInputValue,
  formatTradingTime,
  formatTradingTimezoneOffset,
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
});
