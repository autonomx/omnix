import { useEffect, useMemo, useState } from 'react';
import { tradingApi } from './tradingApi';
import type { CanonicalInstrument, TradingDocument } from './tradingTypes';
import './TradingWatchlist.css';

type WatchlistPayload = { name: string; instrumentIds: string[] };
type QuoteSnapshot = { price: string | null; changePercent: number | null };

function payload(record: TradingDocument | null): WatchlistPayload {
  const value = record?.payload as Partial<WatchlistPayload> | undefined;
  return {
    name: typeof value?.name === 'string' ? value.name : 'Watchlist',
    instrumentIds: Array.isArray(value?.instrumentIds)
      ? value.instrumentIds.filter((item): item is string => typeof item === 'string')
      : [],
  };
}

function formatPrice(value: string | null | undefined): string {
  if (!value) return '—';
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? numeric.toLocaleString('en-US', { maximumFractionDigits: 8 })
    : value;
}

function formatChange(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function defaultWatchlistInstrumentIds(instruments: CanonicalInstrument[]): string[] {
  const equities = instruments
    .filter((instrument) => instrument.asset_class === 'equity')
    .map((instrument) => instrument.instrument_id);
  const otherInstruments = instruments
    .filter((instrument) => instrument.asset_class !== 'equity')
    .map((instrument) => instrument.instrument_id);
  return [...equities, ...otherInstruments];
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
  const [quotes, setQuotes] = useState<Record<string, QuoteSnapshot>>({});
  const [optionsOpen, setOptionsOpen] = useState(false);
  const selected = records.find((record) => record.record_id === selectedId) ?? records[0] ?? null;
  const current = payload(selected);
  const instrumentIdsKey = current.instrumentIds.join('\u0000');
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
          instrumentIds: defaultWatchlistInstrumentIds(instruments),
        });
        next = [created];
      } else {
        const defaultRecord = next.find((record) => record.record_id === 'default');
        if (defaultRecord) {
          const defaultPayload = payload(defaultRecord);
          const orderedInstrumentIds = defaultWatchlistInstrumentIds(instruments);
          const availableIds = new Set(orderedInstrumentIds);
          const retainedIds = defaultPayload.instrumentIds.filter((instrumentId) => !availableIds.has(instrumentId));
          const mergedIds = [...orderedInstrumentIds, ...retainedIds];
          const hasChanged = mergedIds.length !== defaultPayload.instrumentIds.length
            || mergedIds.some((instrumentId, index) => instrumentId !== defaultPayload.instrumentIds[index]);
          if (hasChanged) {
            try {
              const updated = await tradingApi.updateDocument('watchlists', defaultRecord, {
                ...defaultPayload,
                instrumentIds: mergedIds,
              });
              next = next.map((record) => record.record_id === updated.record_id ? updated : record);
            } catch {
              next = next.map((record) => record.record_id === defaultRecord.record_id
                ? { ...record, payload: { ...record.payload, instrumentIds: mergedIds } }
                : record);
            }
          }
        }
      }
      if (cancelled) return;
      setRecords(next);
      setSelectedId(next[0]?.record_id ?? '');
      setStatus('saved');
    }).catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, [instruments]);

  useEffect(() => {
    const instrumentIds = instrumentIdsKey ? instrumentIdsKey.split('\u0000') : [];
    let cancelled = false;
    if (instrumentIds.length === 0) {
      setQuotes({});
      return () => { cancelled = true; };
    }

    void (async () => {
      const next: Record<string, QuoteSnapshot> = {};
      await Promise.all(instrumentIds.map(async (instrumentId) => {
        try {
          const quote = await tradingApi.quote(instrumentId);
          const rawChange = quote.change_percent ?? quote.changePercent ?? quote.percent_change;
          const parsedChange = rawChange == null ? Number.NaN : Number(rawChange);
          next[instrumentId] = {
            price: quote.price ?? null,
            changePercent: Number.isFinite(parsedChange) ? parsedChange : null,
          };
        } catch {
          next[instrumentId] = { price: null, changePercent: null };
        }
      }));
      if (!cancelled) setQuotes(next);
    })();

    return () => { cancelled = true; };
  }, [instrumentIdsKey]);

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

  const rename = () => {
    const name = window.prompt('Rename watchlist', current.name)?.trim();
    if (name) void save({ ...current, name });
    setOptionsOpen(false);
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
        <button type="button" onClick={addActive} disabled={!activeInstrumentId} aria-label="Add active instrument" title="Add active instrument">+</button>
        <div className="trading-watchlist-options">
          <button
            type="button"
            onClick={() => setOptionsOpen((value) => !value)}
            aria-label="Watchlist options"
            aria-expanded={optionsOpen}
            title="Watchlist options"
          >
            ⋯
          </button>
          {optionsOpen ? (
            <div className="trading-watchlist-options-menu" role="menu">
              <button type="button" role="menuitem" onClick={() => { setOptionsOpen(false); void create(); }}>New watchlist</button>
              <button type="button" role="menuitem" onClick={rename} disabled={!selected}>Rename watchlist</button>
              <button type="button" role="menuitem" onClick={() => { setOptionsOpen(false); void archive(); }} disabled={records.length <= 1}>Delete watchlist</button>
            </div>
          ) : null}
        </div>
      </div>
      <div className="trading-watchlist-columns" aria-hidden="true">
        <span>Symbol</span>
        <span>Last</span>
        <span>Chg%</span>
      </div>
      <ul>
        {current.instrumentIds.map((instrumentId, index) => {
          const instrument = instrumentById.get(instrumentId);
          const symbol = instrument?.display_symbol ?? instrumentId;
          const quote = quotes[instrumentId];
          const baseCurrency = instrument?.base_currency ?? symbol.slice(0, 1);
          return (
            <li key={instrumentId} className={instrumentId === activeInstrumentId ? 'active' : undefined}>
              <button type="button" onClick={() => onSelect(instrumentId)} aria-label={`Select ${symbol}`}>
                <span className="trading-watchlist-asset-icon" aria-hidden="true">{baseCurrency.slice(0, 1)}</span>
                <strong>{symbol}</strong>
              </button>
              <span className="trading-watchlist-price">{formatPrice(quote?.price)}</span>
              <span className={`trading-watchlist-change${quote?.changePercent != null ? (quote.changePercent >= 0 ? ' positive' : ' negative') : ''}`}>
                {formatChange(quote?.changePercent)}
              </span>
              <span className="trading-watchlist-row-actions">
                <button type="button" onClick={() => move(index, -1)} aria-label={`Move ${symbol} up`}>↑</button>
                <button type="button" onClick={() => move(index, 1)} aria-label={`Move ${symbol} down`}>↓</button>
                <button type="button" onClick={() => void save({ ...current, instrumentIds: current.instrumentIds.filter((id) => id !== instrumentId) })} aria-label={`Remove ${symbol}`}>×</button>
              </span>
            </li>
          );
        })}
      </ul>
      <span className="trading-watchlist-status" aria-live="polite">{status}</span>
    </section>
  );
}
