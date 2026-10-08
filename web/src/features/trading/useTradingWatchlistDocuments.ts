import { useEffect, useMemo, useState } from 'react';
import { tradingApi } from './tradingApi';
import type { CanonicalInstrument, TradingDocument } from './tradingTypes';
import {
  flagListColor,
  isNewerWatchlistPayload,
  newWatchlistPayload,
  serializeWatchlist,
  upgradeWatchlistPayload,
  watchlistSymbolsNeedRewrite,
  type WatchlistPayload,
} from './tradingWatchlistModel';

export type WatchlistSaveStatus = 'loading' | 'saved' | 'saving' | 'conflict' | 'error';

/** A change to a list, applied to whichever revision is current when it is saved. */
export type WatchlistOperation = (payload: WatchlistPayload) => WatchlistPayload;

const MAX_CONFLICT_RETRIES = 3;

function isConflictError(error: unknown): boolean {
  return error instanceof Error && error.message.includes('(409)');
}

function defaultWatchlistInstrumentIds(instruments: CanonicalInstrument[]): string[] {
  const equities = instruments
    .filter((instrument) => instrument.asset_class === 'equity')
    .map((instrument) => instrument.instrument_id);
  const crypto = instruments
    .filter((instrument) => instrument.asset_class === 'crypto' && instrument.venue === 'BINANCE')
    .map((instrument) => instrument.instrument_id);
  return [...equities, ...crypto];
}

/**
 * The user's watchlist documents and the selected list. `selectedListId` is a
 * watchlist record id or a generated flag list (`flag:<colour>`); `selected`
 * is null while a flag list is shown.
 */
export function useTradingWatchlistDocuments(instruments: CanonicalInstrument[]) {
  const [records, setRecords] = useState<TradingDocument[]>([]);
  const [selectedListId, setSelectedListId] = useState('');
  const [status, setStatus] = useState<WatchlistSaveStatus>('loading');
  const flagColor = flagListColor(selectedListId);
  const selected = flagColor ? null : records.find((record) => record.record_id === selectedListId) ?? records[0] ?? null;
  const current = useMemo(() => upgradeWatchlistPayload(selected?.payload), [selected]);
  // Written by a newer Omnix: shown from its `instrumentIds`, never saved over.
  const readOnly = selected != null && isNewerWatchlistPayload(selected.payload);

  useEffect(() => {
    let cancelled = false;
    void tradingApi.documents('watchlists').then(async (loaded) => {
      if (cancelled) return;
      let next = loaded;
      if (next.length === 0) {
        const created = await tradingApi.createDocument(
          'watchlists',
          'default',
          serializeWatchlist(newWatchlistPayload('Default Watchlist', defaultWatchlistInstrumentIds(instruments))),
        );
        next = [created];
      } else {
        const defaultRecord = next.find((record) => record.record_id === 'default');
        // Built-in symbols are only seed data for a newly created watchlist.
        // Re-adding them here would resurrect symbols the user deliberately
        // removed after a reload or server restart. Only legacy crypto ids and
        // duplicates are rewritten.
        if (defaultRecord && !isNewerWatchlistPayload(defaultRecord.payload) && watchlistSymbolsNeedRewrite(defaultRecord.payload)) {
          const upgraded = serializeWatchlist(upgradeWatchlistPayload(defaultRecord.payload));
          try {
            const updated = await tradingApi.updateDocument('watchlists', defaultRecord, upgraded);
            next = next.map((record) => record.record_id === updated.record_id ? updated : record);
          } catch {
            next = next.map((record) => record.record_id === defaultRecord.record_id
              ? { ...record, payload: upgraded }
              : record);
          }
        }
      }
      if (cancelled) return;
      setRecords(next);
      setSelectedListId((currentListId) => (
        flagListColor(currentListId) || next.some((record) => record.record_id === currentListId)
          ? currentListId
          : next[0]?.record_id ?? ''
      ));
      setStatus('saved');
    }).catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, [instruments]);

  const replace = (record: TradingDocument) => {
    setRecords((items) => items.map((item) => item.record_id === record.record_id ? record : item));
  };

  /**
   * Save `operation` applied to `base`. On a revision conflict the latest
   * revision is loaded and the operation applied to it again, so a change
   * made elsewhere (another tab, another device) is kept rather than
   * overwritten. A failed save shows the last known server revision.
   */
  const persist = async (base: TradingDocument, operation: WatchlistOperation) => {
    setStatus('saving');
    let record = base;
    for (let attempt = 0; ; attempt += 1) {
      if (isNewerWatchlistPayload(record.payload)) {
        replace(record);
        setStatus('conflict');
        return;
      }
      try {
        const saved = await tradingApi.updateDocument('watchlists', record, serializeWatchlist(operation(upgradeWatchlistPayload(record.payload))));
        replace(saved);
        setStatus('saved');
        return;
      } catch (error) {
        const latest = isConflictError(error) && attempt < MAX_CONFLICT_RETRIES
          ? (await tradingApi.documents('watchlists').catch(() => []))
            .find((item) => item.record_id === record.record_id)
          : undefined;
        if (!latest) {
          replace(record);
          setStatus(isConflictError(error) ? 'conflict' : 'error');
          return;
        }
        record = latest;
        replace({ ...latest, payload: serializeWatchlist(operation(upgradeWatchlistPayload(latest.payload))) });
      }
    }
  };

  /** Show a change at once and persist it as an operation. Read-only lists ignore changes. */
  const commit = (operation: WatchlistOperation) => {
    if (!selected || readOnly) return;
    replace({ ...selected, payload: serializeWatchlist(operation(current)) });
    void persist(selected, operation);
  };

  /** Create and select a watchlist; false when it could not be saved. */
  const create = async (payload: WatchlistPayload = newWatchlistPayload(`Watchlist ${records.length + 1}`)): Promise<boolean> => {
    setStatus('saving');
    try {
      const record = await tradingApi.createDocument('watchlists', `watchlist-${Date.now()}`, serializeWatchlist(payload));
      setRecords((items) => [...items, record]);
      setSelectedListId(record.record_id);
      setStatus('saved');
      return true;
    } catch {
      setStatus('error');
      return false;
    }
  };

  const archive = async () => {
    if (!selected || records.length <= 1) return;
    setStatus('saving');
    try {
      await tradingApi.archiveDocument('watchlists', selected);
      const next = records.filter((item) => item.record_id !== selected.record_id);
      setRecords(next);
      setSelectedListId(next[0]?.record_id ?? '');
      setStatus('saved');
    } catch (error) {
      setStatus(isConflictError(error) ? 'conflict' : 'error');
    }
  };

  return {
    records,
    selectedListId,
    setSelectedListId,
    flagColor,
    selected,
    current,
    readOnly,
    status,
    commit,
    create,
    archive,
  };
}
