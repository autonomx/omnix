import { useEffect, useMemo, useState } from 'react';
import { tradingApi } from './tradingApi';
import type { CanonicalInstrument, TradingDocument } from './tradingTypes';
import './TradingWatchlist.css';

type WatchlistPayload = { name: string; instrumentIds: string[] };

function payload(record: TradingDocument | null): WatchlistPayload {
  const value = record?.payload as Partial<WatchlistPayload> | undefined;
  return {
    name: typeof value?.name === 'string' ? value.name : 'Watchlist',
    instrumentIds: Array.isArray(value?.instrumentIds)
      ? value.instrumentIds.filter((item): item is string => typeof item === 'string')
      : [],
  };
}

export function TradingWatchlist({
  instruments,
  activeInstrumentId,
  onSelect,
}: {
  instruments: CanonicalInstrument[];
  activeInstrumentId: string;
  onSelect: (instrumentId: string) => void;
}) {
  const [records, setRecords] = useState<TradingDocument[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [status, setStatus] = useState<'loading' | 'saved' | 'saving' | 'conflict' | 'error'>('loading');
  const selected = records.find((record) => record.record_id === selectedId) ?? records[0] ?? null;
  const current = payload(selected);
  const instrumentById = useMemo(
    () => new Map(instruments.map((instrument) => [instrument.instrument_id, instrument])),
    [instruments],
  );

  useEffect(() => {
    let cancelled = false;
    void tradingApi.documents('watchlists').then(async (loaded) => {
      if (cancelled) return;
      let next = loaded;
      if (next.length === 0) {
        const created = await tradingApi.createDocument('watchlists', 'default', {
          name: 'Default Watchlist',
          instrumentIds: instruments.map((instrument) => instrument.instrument_id),
        });
        next = [created];
      }
      if (cancelled) return;
      setRecords(next);
      setSelectedId(next[0]?.record_id ?? '');
      setStatus('saved');
    }).catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, [instruments]);

  const replace = (record: TradingDocument) => {
    setRecords((items) => items.map((item) => item.record_id === record.record_id ? record : item));
  };

  const save = async (nextPayload: WatchlistPayload) => {
    if (!selected) return;
    setStatus('saving');
    try {
      const next = await tradingApi.updateDocument('watchlists', selected, nextPayload as unknown as Record<string, unknown>);
      replace(next);
      setStatus('saved');
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
    }
  };

  const create = async () => {
    setStatus('saving');
    try {
      const recordId = `watchlist-${Date.now()}`;
      const record = await tradingApi.createDocument('watchlists', recordId, {
        name: `Watchlist ${records.length + 1}`,
        instrumentIds: [],
      });
      setRecords((items) => [...items, record]);
      setSelectedId(record.record_id);
      setStatus('saved');
    } catch {
      setStatus('error');
    }
  };

  const archive = async () => {
    if (!selected || records.length <= 1) return;
    setStatus('saving');
    try {
      await tradingApi.archiveDocument('watchlists', selected);
      const next = records.filter((item) => item.record_id !== selected.record_id);
      setRecords(next);
      setSelectedId(next[0]?.record_id ?? '');
      setStatus('saved');
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
    }
  };

  const addActive = () => {
    if (!activeInstrumentId || current.instrumentIds.includes(activeInstrumentId)) return;
    void save({ ...current, instrumentIds: [...current.instrumentIds, activeInstrumentId] });
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= current.instrumentIds.length) return;
    const next = [...current.instrumentIds];
    [next[index], next[target]] = [next[target], next[index]];
    void save({ ...current, instrumentIds: next });
  };

  return (
    <section className="trading-watchlist" aria-label="Trading watchlists">
      <div className="trading-watchlist-controls">
        <select value={selected?.record_id ?? ''} onChange={(event) => setSelectedId(event.target.value)} aria-label="Watchlist">
          {records.map((record) => <option key={record.record_id} value={record.record_id}>{payload(record).name}</option>)}
        </select>
        <button type="button" onClick={() => void create()} aria-label="Create watchlist">+</button>
        <button type="button" onClick={() => void archive()} disabled={records.length <= 1} aria-label="Delete watchlist">−</button>
      </div>
      {selected ? (
        <label className="trading-watchlist-name">
          Name
          <input value={current.name} onChange={(event) => void save({ ...current, name: event.target.value })} />
        </label>
      ) : null}
      <button type="button" onClick={addActive}>Add active instrument</button>
      <small className={`watchlist-${status}`}>{status}</small>
      <ul>
        {current.instrumentIds.map((instrumentId, index) => {
          const instrument = instrumentById.get(instrumentId);
          return (
            <li key={instrumentId}>
              <button type="button" onClick={() => onSelect(instrumentId)}>
                <strong>{instrument?.display_symbol ?? instrumentId}</strong>
                <small>{instrument?.venue ?? 'Unknown venue'}</small>
              </button>
              <span>
                <button type="button" onClick={() => move(index, -1)} aria-label="Move up">↑</button>
                <button type="button" onClick={() => move(index, 1)} aria-label="Move down">↓</button>
                <button type="button" onClick={() => void save({ ...current, instrumentIds: current.instrumentIds.filter((id) => id !== instrumentId) })} aria-label="Remove">×</button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
