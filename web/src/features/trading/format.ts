/** Display formatting shared by the trading panels. One reading of a missing value, one minus sign. */

export const MISSING = '—';

/** A finite number, or null for null, undefined, '' and anything that does not parse. */
export function numericValue(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** `+1.25R`, `-0.40`: a fixed-digit number with a leading `+` on gains. A missing value reads as `—`. */
export function formatSigned(value: unknown, digits = 2, suffix = ''): string {
  const parsed = numericValue(value);
  if (parsed === null) return MISSING;
  return `${parsed > 0 ? '+' : ''}${parsed.toFixed(digits)}${suffix}`;
}

/** `1,234.50 USD`, `-12.00 USD`; with `signed`, gains read `+12.00 USD`. A missing amount reads as `—`. */
export function formatMoney(value: unknown, currency = 'USD', { signed = false }: { signed?: boolean } = {}): string {
  const parsed = numericValue(value);
  if (parsed === null) return MISSING;
  const sign = parsed < 0 ? '-' : signed && parsed > 0 ? '+' : '';
  const absolute = Math.abs(parsed).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${sign}${absolute} ${currency}`;
}
