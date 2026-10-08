import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { tradingApi } from './tradingApi';
import type { TradingDocument } from './tradingTypes';
import {
  WATCHLIST_FLAGS_RECORD_ID,
  emptyWatchlistFlags,
  readWatchlistFlags,
  setWatchlistFlags,
  watchlistFlagMap,
  type WatchlistFlagColor,
  type WatchlistFlagsPayload,
} from './tradingWatchlistModel';

type FlagsStatus = 'loading' | 'ready' | 'saving' | 'error';

function isConflict(error: unknown): boolean {
  return error instanceof Error && error.message.includes('(409)');
}

async function latestFlagsRecord(): Promise<TradingDocument | null> {
  const records = await tradingApi.documents('watchlist-flags');
  return records.find((record) => record.record_id === WATCHLIST_FLAGS_RECORD_ID) ?? null;
}

/**
 * The user's colour flags (TVP-5.1). Writes are applied as operations, so a
 * revision conflict (another tab flagged a symbol) re-applies the change to
 * the latest document instead of overwriting it. Chart and screener entry
 * points can share this hook when they gain a flag action.
 */
export function useTradingWatchlistFlags() {
  const [payload, setPayload] = useState<WatchlistFlagsPayload>(emptyWatchlistFlags);
  const [status, setStatus] = useState<FlagsStatus>('loading');
  const recordRef = useRef<TradingDocument | null>(null);

  useEffect(() => {
    let cancelled = false;
    void latestFlagsRecord().then((loaded) => {
      if (cancelled) return;
      recordRef.current = loaded;
      setPayload(readWatchlistFlags(loaded?.payload));
      setStatus('ready');
    }).catch(() => {
      if (!cancelled) setStatus('error');
    });
    return () => { cancelled = true; };
  }, []);

  const setFlag = useCallback(async (instrumentIds: readonly string[], color: WatchlistFlagColor | null) => {
    if (instrumentIds.length === 0) return;
    const previous = { record: recordRef.current, payload: readWatchlistFlags(recordRef.current?.payload) };
    setPayload((current) => setWatchlistFlags(current, instrumentIds, color));
    setStatus('saving');
    let current = recordRef.current;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const next = setWatchlistFlags(readWatchlistFlags(current?.payload), instrumentIds, color);
      try {
        const saved = current
          ? await tradingApi.updateDocument('watchlist-flags', current, next as unknown as Record<string, unknown>)
          : await tradingApi.createDocument('watchlist-flags', WATCHLIST_FLAGS_RECORD_ID, next as unknown as Record<string, unknown>);
        recordRef.current = saved;
        setPayload(readWatchlistFlags(saved.payload));
        setStatus('ready');
        return;
      } catch (error) {
        if (!isConflict(error) || attempt === 3) break;
        current = await latestFlagsRecord().catch(() => current);
      }
    }
    recordRef.current = previous.record;
    setPayload(previous.payload);
    setStatus('error');
  }, []);

  const flags = useMemo(() => watchlistFlagMap(payload), [payload]);
  return { payload, flags, status, setFlag };
}
