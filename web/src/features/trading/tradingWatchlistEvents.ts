/**
 * Trading's watchlist requests on the in-page bus: another panel (the screener, TVP-9.1) asks the open watchlist to
 * add symbols; the watchlist adds the ones it doesn't have, as one edit.
 */
import { useEffect, useRef } from 'react';
import { emitOmnixEvent, onOmnixEvent } from '../../events/bus';

declare module '../../events/bus' {
  interface OmnixEventMap {
    'omnix:trading-watchlist-add': { instrumentIds: string[] };
  }
}

export function requestWatchlistAdd(instrumentIds: readonly string[]): void {
  if (instrumentIds.length > 0) emitOmnixEvent('omnix:trading-watchlist-add', { instrumentIds: [...instrumentIds] });
}

/** The open watchlist's side: `add` receives the requested symbols while `enabled` (a list is open and editable). */
export function useWatchlistAddRequests(add: (instrumentIds: string[]) => void, enabled: boolean): void {
  const handler = useRef(add);
  useEffect(() => {
    handler.current = add;
  });
  useEffect(() => (enabled ? onOmnixEvent('omnix:trading-watchlist-add', ({ instrumentIds }) => handler.current(instrumentIds)) : undefined), [enabled]);
}
