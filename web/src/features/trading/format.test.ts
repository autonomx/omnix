import { describe, expect, it } from 'vitest';
import { formatMoney, formatSigned, MISSING, numericValue } from './format';

describe('trading format', () => {
  it.each([
    [null, null],
    [undefined, null],
    ['', null],
    ['abc', null],
    [Number.NaN, null],
    [Number.POSITIVE_INFINITY, null],
    ['12.5', 12.5],
    [0, 0],
    [-3, -3],
  ])('reads %p as %p', (value, expected) => {
    expect(numericValue(value)).toBe(expected);
  });

  it('reads a missing amount as a dash, not as zero', () => {
    expect(formatMoney(null)).toBe(MISSING);
    expect(formatMoney(undefined, 'USD', { signed: true })).toBe(MISSING);
    expect(formatMoney('')).toBe(MISSING);
  });

  it('formats amounts with two decimals and the currency code', () => {
    expect(formatMoney(96500)).toBe('96,500.00 USD');
    expect(formatMoney('-12', 'EUR')).toBe('-12.00 EUR');
    expect(formatMoney(125.5)).toBe('125.50 USD');
  });

  it('marks gains only when signed', () => {
    expect(formatMoney(125.5, 'USD', { signed: true })).toBe('+125.50 USD');
    expect(formatMoney(-125.5, 'USD', { signed: true })).toBe('-125.50 USD');
    expect(formatMoney(0, 'USD', { signed: true })).toBe('0.00 USD');
  });

  it('formats signed numbers with a suffix', () => {
    expect(formatSigned(1.25, 2, 'R')).toBe('+1.25R');
    expect(formatSigned('-0.4')).toBe('-0.40');
    expect(formatSigned(null)).toBe(MISSING);
  });
});
