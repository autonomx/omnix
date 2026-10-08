import { isIntervalAvailable, TRADING_VIEW_INTERVAL_GROUPS } from './tradingIntervals';

export type IntervalInputResult =
  | { ok: true; interval: string }
  | { ok: false; error: string };

const KNOWN_INTERVALS = new Set(TRADING_VIEW_INTERVAL_GROUPS.flatMap((group) => group.options.map((option) => option.value)));

/** TradingView's typed units. `m` is minutes and `M` is months, so the case matters for those two only. */
function unitFor(unit: string): string | null {
  if (unit === '' || unit === 'm') return 'm';
  if (unit === 'M' || unit.toLowerCase() === 'mo') return 'mo';
  const lower = unit.toLowerCase();
  return ['t', 's', 'h', 'd', 'w', 'r'].includes(lower) ? lower : null;
}

/**
 * Reads what was typed in the interval box: a number, optionally followed by
 * a unit (`5`, `15`, `1h`, `1D`, `3s`, `100t`, `1M`). A plain number is
 * minutes, and whole hours of minutes become hours (`60` is `1h`). Only the
 * intervals Omnix offers are accepted; custom intervals are TVP-2.5.
 */
export function parseTradingIntervalInput(text: string): string | null {
  const match = text.trim().match(/^(\d+)\s*([a-zA-Z]{0,2})$/);
  if (!match) return null;
  let amount = Number(match[1]);
  let unit = unitFor(match[2]);
  if (!unit || !Number.isSafeInteger(amount) || amount <= 0) return null;
  if (unit === 'm' && amount >= 60 && amount % 60 === 0) {
    amount /= 60;
    unit = 'h';
  }
  const interval = `${amount}${unit}`;
  return KNOWN_INTERVALS.has(interval) ? interval : null;
}

/** Parses typed text and checks the chart's feed can show that interval. */
export function resolveTradingIntervalInput(text: string, supportedIntervals: readonly string[]): IntervalInputResult {
  const interval = parseTradingIntervalInput(text);
  if (!interval) return { ok: false, error: `“${text.trim()}” is not an interval Omnix offers.` };
  if (supportedIntervals.length > 0 && !isIntervalAvailable(interval, supportedIntervals)) {
    return { ok: false, error: `The chart's data feed doesn't support ${interval}.` };
  }
  return { ok: true, interval };
}
