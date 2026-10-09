// Screener auto-refresh (TVP-9.2): a saved screen re-runs every 10 s or every
// minute while the screener is open, and the results say what changed since
// the previous run. A run is started only when none of the screen's runs is
// still working, so a slow run never stacks up behind itself; the server's
// own limits (concurrency, runtime) bound each run.
import { useEffect, useRef } from 'react';
import { startPolling } from '../../shared/timers';
import type { TradingScannerResult } from './scannerTypes';

export const AUTO_REFRESH_OPTIONS = [
  { value: 0, label: 'Off' },
  { value: 10_000, label: 'Every 10 s' },
  { value: 60_000, label: 'Every minute' },
] as const;

export type AutoRefresh = { scannerId: string; everyMs: number };

/** What changed between two runs' results: the instruments that are new, and those that dropped out. */
export function resultChanges(previous: readonly TradingScannerResult[] | null, next: readonly TradingScannerResult[]): { added: ReadonlySet<string>; removed: string[] } {
  if (previous === null) return { added: new Set(), removed: [] };
  const before = new Set(previous.map((result) => result.instrument_id));
  const after = new Set(next.map((result) => result.instrument_id));
  return {
    added: new Set([...after].filter((id) => !before.has(id))),
    removed: [...before].filter((id) => !after.has(id)),
  };
}

/** Starts the screen's runs on its cadence while mounted; `busy` says whether one of its runs is still working. */
export function useScannerAutoRefresh(auto: AutoRefresh | null, busy: (scannerId: string) => boolean, start: (scannerId: string) => Promise<unknown>): void {
  const latest = useRef({ busy, start });
  useEffect(() => {
    latest.current = { busy, start };
  });
  const scannerId = auto?.scannerId;
  const everyMs = auto?.everyMs ?? 0;
  useEffect(() => {
    if (!scannerId || everyMs <= 0) return;
    return startPolling(() => {
      if (!latest.current.busy(scannerId)) void latest.current.start(scannerId).catch(() => undefined);
    }, everyMs);
  }, [scannerId, everyMs]);
}
