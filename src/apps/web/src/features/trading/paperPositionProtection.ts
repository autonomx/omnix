export type PaperPositionProtection = {
  takeProfit: number | null;
  stopLoss: number | null;
};

export const PAPER_POSITION_PROTECTION_EVENT = 'omnix:paper-position-protection-changed';

const storageKey = 'omnix.trading.paper-position-protection';

function entryKey(accountId: string, instrumentId: string): string {
  return `${accountId}:${instrumentId}`;
}

function validPrice(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function readAll(): Record<string, PaperPositionProtection> {
  if (typeof window === 'undefined') return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(storageKey) ?? '{}');
    if (!parsed || typeof parsed !== 'object') return {};
    return Object.entries(parsed as Record<string, unknown>).reduce<Record<string, PaperPositionProtection>>((result, [key, value]) => {
      if (!value || typeof value !== 'object') return result;
      const item = value as Record<string, unknown>;
      result[key] = { takeProfit: validPrice(item.takeProfit), stopLoss: validPrice(item.stopLoss) };
      return result;
    }, {});
  } catch {
    return {};
  }
}

export function readPaperPositionProtection(accountId: string, instrumentId: string): PaperPositionProtection {
  return readAll()[entryKey(accountId, instrumentId)] ?? { takeProfit: null, stopLoss: null };
}

export function writePaperPositionProtection(
  accountId: string,
  instrumentId: string,
  protection: PaperPositionProtection,
): void {
  if (typeof window === 'undefined') return;
  const values = readAll();
  const key = entryKey(accountId, instrumentId);
  const normalized = { takeProfit: validPrice(protection.takeProfit), stopLoss: validPrice(protection.stopLoss) };
  if (normalized.takeProfit === null && normalized.stopLoss === null) delete values[key];
  else values[key] = normalized;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(values));
  } catch {
    // The overlay remains usable for the current session when storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent(PAPER_POSITION_PROTECTION_EVENT, { detail: { accountId, instrumentId } }));
}

