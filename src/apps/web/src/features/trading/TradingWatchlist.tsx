import { useEffect, useMemo, useState } from 'react';
import { tradingApi } from './tradingApi';
import { binanceInstrumentIdFor } from './cryptoInstrumentDefaults';
import type { CanonicalInstrument, ProviderBinding, TradingDocument } from './tradingTypes';
import { isIntervalAvailable, tradingIntervalMinutes } from './tradingIntervals';
import { percentChangeFromBars, percentChangeFromLookback } from './tradingWatchlistChange';
import {
  formatWatchlistPrice,
  watchlistDisplaySymbol,
  watchlistLogoIdentity,
} from './tradingWatchlistPresentation';
import { TradingWatchlistSymbolPicker } from './TradingWatchlistSymbolPicker';
import './TradingWatchlist.css';

type WatchlistPayload = { name: string; instrumentIds: string[] };
type QuoteSnapshot = { price: string | null; changePercent: number | null };
type ChangeSort = 'manual' | 'desc' | 'asc';

// The side-panel tabs unmount the watchlist when another tab is selected. Keep
// the latest values at module scope so returning to the watchlist can render
// them immediately while the next refresh is in flight.
const watchlistQuoteCache: Record<string, QuoteSnapshot> = {};

const fallbackIntervals = ['1mo', '1w', '1d', '12h', '8h', '6h', '4h', '2h', '1h', '30m', '15m', '5m', '3m', '1m'];

function fallbackIntervalCandidates(interval: string): string[] {
  const targetMinutes = tradingIntervalMinutes(interval);
  if (targetMinutes == null) return [];
  return fallbackIntervals.filter((candidate) => {
    const candidateMinutes = tradingIntervalMinutes(candidate);
    return candidate !== interval && candidateMinutes != null && candidateMinutes < targetMinutes;
  });
}

function fallbackLimit(interval: string, baseInterval: string): number {
  const targetMinutes = tradingIntervalMinutes(interval) ?? 1;
  const baseMinutes = tradingIntervalMinutes(baseInterval) ?? targetMinutes;
  return Math.min(5_000, Math.max(2, Math.ceil(targetMinutes / baseMinutes) + 3));
}

async function intervalChange(
  instrumentId: string,
  interval: string,
  quotePrice: string | null | undefined,
  directBars: Awaited<ReturnType<typeof tradingApi.bars>> | null,
  supportedIntervals?: readonly string[],
): Promise<{ price: string | null; changePercent: number | null }> {
  const directHistory = directBars?.bars ?? [];
  const directPrice = quotePrice ?? directHistory.at(-1)?.close?.toString() ?? null;
  if (supportedIntervals && !isIntervalAvailable(interval, supportedIntervals)) {
    return { price: directPrice, changePercent: null };
  }
  const directIntervalIsNative = directBars?.binding.supported_intervals.includes(interval) ?? false;
  const directChange = directIntervalIsNative
    ? percentChangeFromBars(quotePrice, directHistory)
    : null;
  if (directChange != null) return { price: directPrice, changePercent: directChange };

  for (const baseInterval of fallbackIntervalCandidates(interval)) {
    const fallback = await tradingApi.bars(instrumentId, baseInterval, fallbackLimit(interval, baseInterval)).catch(() => null);
    const fallbackBars = fallback?.bars ?? [];
    const derivedChange = percentChangeFromLookback(quotePrice, fallbackBars, interval);
    if (derivedChange != null) {
      return {
        price: quotePrice ?? fallbackBars.at(-1)?.close?.toString() ?? directPrice,
        changePercent: derivedChange,
      };
    }
  }

  return { price: directPrice, changePercent: null };
}

function payload(record: TradingDocument | null): WatchlistPayload {
  const value = record?.payload as Partial<WatchlistPayload> | undefined;
  return {
    name: typeof value?.name === 'string' ? value.name : 'Watchlist',
    instrumentIds: Array.isArray(value?.instrumentIds)
      ? value.instrumentIds.filter((item): item is string => typeof item === 'string')
      : [],
  };
}

function formatChange(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function TradingWatchlistLogo({ symbol, instrumentId }: { symbol: string; instrumentId: string }) {
  const identity = watchlistLogoIdentity(symbol, instrumentId);
  return (
    <span
      className={`trading-watchlist-asset-icon ${identity.kind}`}
      role="img"
      aria-label={`${identity.label} logo`}
      title={identity.label}
    >
      {identity.kind === 'apple' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M15.9 5.1c.7-.9 1.2-2.1 1.1-3.3-1.1.1-2.4.8-3.2 1.7-.7.8-1.3 2-1.1 3.1 1.2.1 2.4-.6 3.2-1.5ZM19.9 13.1c0-2.5 2.1-3.7 2.2-3.8-1.2-1.7-3.1-1.9-3.8-1.9-1.6-.2-3.1 1-3.9 1-.8 0-2-.9-3.3-.9-1.7 0-3.3 1-4.2 2.5-1.8 3-.5 7.4 1.3 9.8.9 1.2 1.9 2.5 3.2 2.4 1.3-.1 1.8-.8 3.4-.8s2 .8 3.3.8c1.4 0 2.2-1.2 3.1-2.5 1-1.4 1.4-2.8 1.4-2.9-.1 0-2.7-1-2.7-3.7Z" />
        </svg>
      ) : identity.kind === 'nvidia' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 12c2.5-4 5.5-6 9-6s6.5 2 9 6c-2.5 4-5.5 6-9 6s-6.5-2-9-6Z" />
          <path d="M8 16V8l8 8V8" />
        </svg>
      ) : identity.kind === 'tesla' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6c2.4-1.3 5.1-1.8 8-1.8S17.6 4.7 20 6M6 7h12M12 7v12" />
        </svg>
      ) : identity.kind === 'bitcoin' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 5v14M13 5v14M7 8h6.1c2.1 0 3.4 1 3.4 2.5S15.2 13 13.1 13H7m0 0h6.8c2.2 0 3.5 1.1 3.5 2.7S15.8 18 13.5 18H7" />
        </svg>
      ) : identity.kind === 'ethereum' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m12 2-5 10 5 3 5-3-5-10Z" />
          <path d="m7 13 5 9 5-9-5 3-5-3Z" />
        </svg>
      ) : identity.kind === 'solana' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 7h13l-2 3H3l2-3ZM8 11h13l-2 3H6l2-3ZM5 15h13l-2 3H3l2-3Z" />
        </svg>
      ) : identity.kind === 'hyperliquid' ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 5v14M19 5v14M5 12h14M5 5h5v14h4V5h5" />
        </svg>
      ) : (
        identity.mark
      )}
    </span>
  );
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

function mergeInstruments(
  current: readonly CanonicalInstrument[],
  next: CanonicalInstrument,
): CanonicalInstrument[] {
  return [...new Map([...current, next].map((instrument) => [instrument.instrument_id, instrument])).values()];
}

export function TradingWatchlist({
  instruments,
  activeInstrumentId,
  interval,
  providerBindings = [],
  onSelect,
}: {
  instruments: CanonicalInstrument[];
  activeInstrumentId: string;
  interval: string;
  providerBindings?: readonly ProviderBinding[];
  onSelect: (instrumentId: string) => void;
}) {
  const [records, setRecords] = useState<TradingDocument[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [status, setStatus] = useState<'loading' | 'saved' | 'saving' | 'conflict' | 'error'>('loading');
  const [quotes, setQuotes] = useState<Record<string, QuoteSnapshot>>(() => ({ ...watchlistQuoteCache }));
  const [changeSort, setChangeSort] = useState<ChangeSort>('manual');
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [symbolPickerOpen, setSymbolPickerOpen] = useState(false);
  const [discoveredInstruments, setDiscoveredInstruments] = useState<CanonicalInstrument[]>([]);
  const selected = records.find((record) => record.record_id === selectedId) ?? records[0] ?? null;
  const current = payload(selected);
  const normalizedInstrumentIds = useMemo(
    () => [...new Set(current.instrumentIds.map(binanceInstrumentIdFor))],
    [current.instrumentIds],
  );
  const normalizedActiveInstrumentId = activeInstrumentId
    ? binanceInstrumentIdFor(activeInstrumentId)
    : '';
  const instrumentIdsKey = normalizedInstrumentIds.join('\u0000');
  const catalogInstruments = useMemo(
    () => [...new Map([...instruments, ...discoveredInstruments].map((instrument) => [instrument.instrument_id, instrument])).values()],
    [discoveredInstruments, instruments],
  );
  const instrumentById = useMemo(
    () => new Map(catalogInstruments.map((instrument) => [instrument.instrument_id, instrument])),
    [catalogInstruments],
  );
  const bindingIntervalsByInstrument = useMemo(() => {
    const bindingsByInstrument = new Map<string, readonly string[]>();
    for (const binding of providerBindings) {
      if (!binding.supported_intervals.length || bindingsByInstrument.has(binding.instrument_id)) continue;
      bindingsByInstrument.set(binding.instrument_id, binding.supported_intervals);
    }
    return bindingsByInstrument;
  }, [providerBindings]);

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
          // Built-in symbols are only seed data for a newly created watchlist.
          // Re-adding them here would resurrect symbols the user deliberately
          // removed after a reload or server restart.
          const migratedIds = [...new Set(defaultPayload.instrumentIds.map(binanceInstrumentIdFor))];
          const hasChanged = migratedIds.length !== defaultPayload.instrumentIds.length
            || migratedIds.some((instrumentId, index) => instrumentId !== defaultPayload.instrumentIds[index]);
          if (hasChanged) {
            try {
              const updated = await tradingApi.updateDocument('watchlists', defaultRecord, {
                ...defaultPayload,
                instrumentIds: migratedIds,
              });
              next = next.map((record) => record.record_id === updated.record_id ? updated : record);
            } catch {
              next = next.map((record) => record.record_id === defaultRecord.record_id
                ? { ...record, payload: { ...record.payload, instrumentIds: migratedIds } }
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
      return () => { cancelled = true; };
    }

    void (async () => {
      const next: Record<string, QuoteSnapshot> = {};
      await Promise.all(instrumentIds.map(async (instrumentId) => {
        const supportedIntervals = bindingIntervalsByInstrument.get(instrumentId);
        try {
          const quotePromise = tradingApi.quote(instrumentId).catch(() => null);
          const barsPromise = supportedIntervals && !isIntervalAvailable(interval, supportedIntervals)
            ? Promise.resolve(null)
            : tradingApi.bars(instrumentId, interval, 2).catch(() => null);
          const [quote, bars] = await Promise.all([
            quotePromise,
            barsPromise,
          ]);
          next[instrumentId] = await intervalChange(instrumentId, interval, quote?.price, bars, supportedIntervals);
        } catch {
          next[instrumentId] = { price: null, changePercent: null };
        }
      }));
      if (!cancelled) {
        setQuotes((current) => {
          const merged = { ...current };
          for (const [instrumentId, snapshot] of Object.entries(next)) {
            // Keep the last known snapshot when a refresh fails. A symbol that
            // has never produced a quote still renders the normal placeholder.
            if (snapshot.price === null && snapshot.changePercent === null) {
              const cached = watchlistQuoteCache[instrumentId] ?? current[instrumentId];
              if (cached) {
                merged[instrumentId] = cached;
                continue;
              }
            }
            watchlistQuoteCache[instrumentId] = snapshot;
            merged[instrumentId] = snapshot;
          }
          return merged;
        });
      }
    })();

    return () => { cancelled = true; };
  }, [instrumentIdsKey, interval]);

  const displayedInstrumentIds = useMemo(() => {
    if (changeSort === 'manual') return normalizedInstrumentIds;
    return normalizedInstrumentIds
      .map((instrumentId, index) => ({
        instrumentId,
        index,
        changePercent: quotes[instrumentId]?.changePercent,
      }))
      .sort((left, right) => {
        const leftChange = left.changePercent;
        const rightChange = right.changePercent;
        if (leftChange == null && rightChange == null) return left.index - right.index;
        if (leftChange == null) return 1;
        if (rightChange == null) return -1;
        if (leftChange === rightChange) return left.index - right.index;
        return changeSort === 'desc' ? rightChange - leftChange : leftChange - rightChange;
      })
      .map(({ instrumentId }) => instrumentId);
  }, [changeSort, normalizedInstrumentIds, quotes]);

  const replace = (record: TradingDocument) => {
    setRecords((items) => items.map((item) => item.record_id === record.record_id ? record : item));
  };

  const save = async (
  nextPayload: WatchlistPayload,
  rollbackRecord?: TradingDocument,
  recordOverride?: TradingDocument,
  conflictRetryCount = 0,
) => {
    const record = recordOverride ?? selected;
    if (!record) return;
    setStatus('saving');
    try {
      const next = await tradingApi.updateDocument('watchlists', record, nextPayload as unknown as Record<string, unknown>);
      replace(next);
      setStatus('saved');
    } catch (error) {
      const isConflict = error instanceof Error && error.message.includes('(409)');
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

  const addInstrument = async (instrument: CanonicalInstrument) => {
    const instrumentId = binanceInstrumentIdFor(instrument.instrument_id);
    setDiscoveredInstruments((items) => mergeInstruments(items, instrument));
    if (!selected || normalizedInstrumentIds.includes(instrumentId) || status === 'saving') return;
    await save({ ...current, instrumentIds: [...normalizedInstrumentIds, instrumentId] });
  };

  const rename = () => {
    const name = window.prompt('Rename watchlist', current.name)?.trim();
    if (name) void save({ ...current, name });
    setOptionsOpen(false);
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= normalizedInstrumentIds.length) return;
    if (!selected) return;
    const next = [...normalizedInstrumentIds];
    [next[index], next[target]] = [next[target], next[index]];
    const rollbackRecord = selected;
    replace({
      ...selected,
      payload: { ...selected.payload, ...current, instrumentIds: next },
    });
    void save({ ...current, instrumentIds: next }, rollbackRecord);
  };

  return (
    <section className="trading-watchlist" aria-label="Trading watchlists">
      <div className="trading-watchlist-controls">
        <select value={selected?.record_id ?? ''} onChange={(event) => setSelectedId(event.target.value)} aria-label="Watchlist">
          {records.map((record) => <option key={record.record_id} value={record.record_id}>{payload(record).name}</option>)}
        </select>
        <button
          type="button"
          onClick={() => setSymbolPickerOpen(true)}
          disabled={!selected || status === 'loading' || status === 'saving'}
          aria-label="Add symbol to watchlist"
          title="Add symbol to watchlist"
        >
          +
        </button>
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
      <div className="trading-watchlist-columns">
        <span>Symbol</span>
        <span>Last</span>
        <button
          type="button"
          className="trading-watchlist-change-sort"
          aria-label={changeSort === 'manual' ? 'Sort watchlist by change percentage descending' : changeSort === 'desc' ? 'Sort watchlist by change percentage ascending' : 'Clear watchlist change percentage sort'}
          aria-pressed={changeSort !== 'manual'}
          title={`Change over ${interval}. Click to sort.`}
          onClick={() => setChangeSort((current) => current === 'manual' ? 'desc' : current === 'desc' ? 'asc' : 'manual')}
        >
          <span>Chg%</span>
          <span aria-hidden="true">{changeSort === 'desc' ? '↓' : changeSort === 'asc' ? '↑' : '↕'}</span>
        </button>
      </div>
      <ul>
        {displayedInstrumentIds.map((instrumentId, index) => {
          const instrument = instrumentById.get(instrumentId);
          const symbol = watchlistDisplaySymbol(instrument?.display_symbol, instrumentId);
          const quote = quotes[instrumentId];
          return (
            <li key={instrumentId} className={instrumentId === normalizedActiveInstrumentId ? 'active' : undefined}>
              <button type="button" onClick={() => onSelect(binanceInstrumentIdFor(instrumentId))} aria-label={`Select ${symbol}`}>
                <TradingWatchlistLogo symbol={symbol} instrumentId={instrumentId} />
                <strong>{symbol}</strong>
              </button>
              <span className="trading-watchlist-price">{formatWatchlistPrice(quote?.price)}</span>
              <span className={`trading-watchlist-change${quote?.changePercent != null ? (quote.changePercent >= 0 ? ' positive' : ' negative') : ''}`}>
                {formatChange(quote?.changePercent)}
              </span>
              <span className={`trading-watchlist-row-actions${changeSort === 'manual' ? '' : ' is-sorted'}`}>
                <button type="button" onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move ${symbol} up`} title="Move up">↑</button>
                <button type="button" onClick={() => move(index, 1)} disabled={index === normalizedInstrumentIds.length - 1} aria-label={`Move ${symbol} down`} title="Move down">↓</button>
                <button type="button" onClick={() => void save({ ...current, instrumentIds: normalizedInstrumentIds.filter((id) => id !== instrumentId) })} aria-label={`Remove ${symbol}`}>×</button>
              </span>
            </li>
          );
        })}
      </ul>
      <span className="trading-watchlist-status" aria-live="polite">{status}</span>
      <TradingWatchlistSymbolPicker
        open={symbolPickerOpen}
        instruments={catalogInstruments}
        selectedInstrumentIds={normalizedInstrumentIds}
        busy={status === 'saving'}
        onAdd={addInstrument}
        onClose={() => setSymbolPickerOpen(false)}
      />
    </section>
  );
}
