import { useEffect, useMemo, useState } from 'react';
import { tradingApi } from './tradingApi';
import type { CanonicalInstrument, TradingDocument } from './tradingTypes';
import {
  flagListColor,
  newWatchlistPayload,
  upgradeWatchlistPayload,
  watchlistSymbolsNeedRewrite,
  type WatchlistPayload,
} from './tradingWatchlistModel';

export type WatchlistSaveStatus = 'loading' | 'saved' | 'saving' | 'conflict' | 'error';

function documentPayload(payload: WatchlistPayload): Record<string, unknown> {
  return payload as unknown as Record<string, unknown>;
}

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

  useEffect(() => {
    let cancelled = false;
    void tradingApi.documents('watchlists').then(async (loaded) => {
      if (cancelled) return;
      let next = loaded;
      if (next.length === 0) {
        const created = await tradingApi.createDocument(
          'watchlists',
          'default',
          documentPayload(newWatchlistPayload('Default Watchlist', defaultWatchlistInstrumentIds(instruments))),
        );
        next = [created];
      } else {
        const defaultRecord = next.find((record) => record.record_id === 'default');
        // Built-in symbols are only seed data for a newly created watchlist.
        // Re-adding them here would resurrect symbols the user deliberately
        // removed after a reload or server restart. Only legacy crypto ids and
        // duplicates are rewritten.
        if (defaultRecord && watchlistSymbolsNeedRewrite(defaultRecord.payload)) {
          const upgraded = documentPayload(upgradeWatchlistPayload(defaultRecord.payload));
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

  const save = async (
    nextPayload: WatchlistPayload,
    rollbackRecord?: TradingDocument,
    recordOverride?: TradingDocument,
    conflictRetryCount = 0,
  ): Promise<void> => {
    const record = recordOverride ?? selected;
    if (!record) return;
    setStatus('saving');
    try {
      const next = await tradingApi.updateDocument('watchlists', record, documentPayload(nextPayload));
      replace(next);
      setStatus('saved');
    } catch (error) {
      const isConflict = isConflictError(error);
      if (conflictRetryCount < 3 && isConflict) {
        try {
          const latest = (await tradingApi.documents('watchlists'))
            .find((item) => item.record_id === record.record_id);
          if (latest) {
            replace(latest);
            await save(nextPayload, rollbackRecord, latest, conflictRetryCount + 1);
            return;
          }
        } catch {
          // Fall through to the normal conflict state when the latest record cannot be loaded.
        }
      }
      if (rollbackRecord) replace(rollbackRecord);
      setStatus(isConflict ? 'conflict' : 'error');
    }
  };

  /** Show a change at once and persist it; a failed save restores the previous list. */
  const commit = (nextPayload: WatchlistPayload) => {
    if (!selected) return;
    replace({ ...selected, payload: documentPayload(nextPayload) });
    void save(nextPayload, selected, selected);
  };

  /** Create and select a watchlist; false when it could not be saved. */
  const create = async (payload: WatchlistPayload = newWatchlistPayload(`Watchlist ${records.length + 1}`)): Promise<boolean> => {
    setStatus('saving');
    try {
      const record = await tradingApi.createDocument('watchlists', `watchlist-${Date.now()}`, documentPayload(payload));
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
    status,
    save,
    commit,
    create,
    archive,
  };
}
