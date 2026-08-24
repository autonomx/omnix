import { tradingPaperApi } from './tradingPaperApi';

export type PaperPositionProtection = {
  takeProfit: number | null;
  stopLoss: number | null;
};

export const PAPER_POSITION_PROTECTION_EVENT = 'omnix:paper-position-protection-changed';

const cache = new Map<string, PaperPositionProtection>();
const inflight = new Set<string>();

function entryKey(accountId: string, instrumentId: string): string {
  return `${accountId}:${instrumentId}`;
}

function validPrice(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function normalized(value: PaperPositionProtection): PaperPositionProtection {
  return { takeProfit: validPrice(value.takeProfit), stopLoss: validPrice(value.stopLoss) };
}

function equal(left: PaperPositionProtection, right: PaperPositionProtection): boolean {
  return left.takeProfit === right.takeProfit && left.stopLoss === right.stopLoss;
}

function notify(accountId: string, instrumentId: string): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(PAPER_POSITION_PROTECTION_EVENT, { detail: { accountId, instrumentId } }));
}

async function hydrate(accountId: string, instrumentId: string): Promise<void> {
  const key = entryKey(accountId, instrumentId);
  if (inflight.has(key)) return;
  inflight.add(key);
  try {
    const value = await tradingPaperApi.protection(accountId, instrumentId);
    const next: PaperPositionProtection = value
      ? { takeProfit: validPrice(value.take_profit), stopLoss: validPrice(value.stop_loss) }
      : { takeProfit: null, stopLoss: null };
    const previous = cache.get(key) ?? { takeProfit: null, stopLoss: null };
    cache.set(key, next);
    if (!equal(previous, next)) notify(accountId, instrumentId);
  } catch {
    // Keep the last rendered cache value. The server remains authority and the
    // next refresh will reconcile it; no browser persistence is used.
  } finally {
    inflight.delete(key);
  }
}

export function readPaperPositionProtection(accountId: string, instrumentId: string): PaperPositionProtection {
  if (typeof window !== 'undefined') void hydrate(accountId, instrumentId);
  return cache.get(entryKey(accountId, instrumentId)) ?? { takeProfit: null, stopLoss: null };
}

export function writePaperPositionProtection(
  accountId: string,
  instrumentId: string,
  protection: PaperPositionProtection,
): void {
  const next = normalized(protection);
  cache.set(entryKey(accountId, instrumentId), next);
  notify(accountId, instrumentId);
  if (typeof window === 'undefined') return;

  const persist = async () => {
    if (next.takeProfit === null && next.stopLoss === null) {
      try {
        await tradingPaperApi.clearProtection(accountId, instrumentId);
      } catch {
        // Clearing an already absent row is effectively idempotent for the UI.
      }
    } else {
      await tradingPaperApi.setProtection(accountId, {
        instrument_id: instrumentId,
        take_profit: next.takeProfit === null ? null : String(next.takeProfit),
        stop_loss: next.stopLoss === null ? null : String(next.stopLoss),
      });
    }
    await hydrate(accountId, instrumentId);
  };
  void persist().catch(() => void hydrate(accountId, instrumentId));
}
