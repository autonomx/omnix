import { useMemo, useState } from 'react';
import { binanceInstrumentIdFor } from './cryptoInstrumentDefaults';
import type { CanonicalInstrument, ProviderBinding } from './tradingTypes';
import { watchlistDisplaySymbol } from './tradingWatchlistPresentation';
import {
  WATCHLIST_FLAG_COLORS,
  WATCHLIST_FLAG_LABELS,
  addWatchlistSection,
  addWatchlistSymbols,
  flagListId,
  flaggedInstrumentIds,
  isSymbolItem,
  moveWatchlistItem,
  removeWatchlistSection,
  removeWatchlistSymbols,
  updateWatchlistSection,
  upgradeWatchlistPayload,
  watchlistRows,
  type WatchlistFlagColor,
  type WatchlistItem,
} from './tradingWatchlistModel';
import { useTradingWatchlistDocuments } from './useTradingWatchlistDocuments';
import { useTradingWatchlistFlags } from './useTradingWatchlistFlags';
import { useTradingWatchlistQuotes } from './useTradingWatchlistQuotes';
import { TradingWatchlistSectionRow, TradingWatchlistSymbolRow } from './TradingWatchlistRows';
import { TradingWatchlistSymbolPicker } from './TradingWatchlistSymbolPicker';
import './TradingWatchlist.css';

type ChangeSort = 'manual' | 'desc' | 'asc';

function mergeInstruments(
  current: readonly CanonicalInstrument[],
  next: CanonicalInstrument,
): CanonicalInstrument[] {
  return [...new Map([...current, next].map((instrument) => [instrument.instrument_id, instrument])).values()];
}

function flagListName(color: WatchlistFlagColor): string {
  return `${WATCHLIST_FLAG_LABELS[color]} flags`;
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
  const {
    records, selectedListId, setSelectedListId, flagColor, selected, current, status, save, commit, create, archive,
  } = useTradingWatchlistDocuments(instruments);
  const { payload: flagsPayload, flags, setFlag } = useTradingWatchlistFlags();
  const [changeSort, setChangeSort] = useState<ChangeSort>('manual');
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [symbolPickerOpen, setSymbolPickerOpen] = useState(false);
  const [flagMenuFor, setFlagMenuFor] = useState<string | null>(null);
  const [discoveredInstruments, setDiscoveredInstruments] = useState<CanonicalInstrument[]>([]);
  const listItems = useMemo<WatchlistItem[]>(
    () => flagColor
      ? flaggedInstrumentIds(flagsPayload, flagColor).map((instrumentId) => ({ type: 'symbol', instrumentId }))
      : current.items,
    [current, flagColor, flagsPayload],
  );
  const instrumentIds = useMemo(() => listItems.filter(isSymbolItem).map((item) => item.instrumentId), [listItems]);
  const quotes = useTradingWatchlistQuotes(instrumentIds, interval, providerBindings);
  const flagListColors = WATCHLIST_FLAG_COLORS.filter((color) => (
    color === flagColor || flagsPayload.flags.some((flag) => flag.color === color)
  ));
  const normalizedActiveInstrumentId = activeInstrumentId ? binanceInstrumentIdFor(activeInstrumentId) : '';
  const catalogInstruments = useMemo(
    () => [...new Map([...instruments, ...discoveredInstruments].map((instrument) => [instrument.instrument_id, instrument])).values()],
    [discoveredInstruments, instruments],
  );
  const instrumentById = useMemo(
    () => new Map(catalogInstruments.map((instrument) => [instrument.instrument_id, instrument])),
    [catalogInstruments],
  );

  const compareSymbols = useMemo(() => {
    if (changeSort === 'manual') return undefined;
    return (left: string, right: string) => {
      const leftChange = quotes[left]?.changePercent;
      const rightChange = quotes[right]?.changePercent;
      if (leftChange == null && rightChange == null) return 0;
      if (leftChange == null) return 1;
      if (rightChange == null) return -1;
      return changeSort === 'desc' ? rightChange - leftChange : leftChange - rightChange;
    };
  }, [changeSort, quotes]);
  const rows = useMemo(() => watchlistRows(listItems, compareSymbols), [compareSymbols, listItems]);
  const sorted = changeSort !== 'manual';
  const listName = flagColor ? flagListName(flagColor).toLowerCase() : 'watchlist';

  const addInstrument = async (instrument: CanonicalInstrument) => {
    const instrumentId = binanceInstrumentIdFor(instrument.instrument_id);
    setDiscoveredInstruments((items) => mergeInstruments(items, instrument));
    if (flagColor) {
      await setFlag([instrumentId], flagColor);
      return;
    }
    if (!selected || instrumentIds.includes(instrumentId) || status === 'saving') return;
    await save(addWatchlistSymbols(current, [instrumentId]));
  };

  const removeInstrument = (instrumentId: string) => {
    if (flagColor) void setFlag([instrumentId], null);
    else commit(removeWatchlistSymbols(current, new Set([instrumentId])));
  };

  const promptName = (title: string, initial: string, apply: (name: string) => void) => {
    setOptionsOpen(false);
    const name = window.prompt(title, initial)?.trim();
    if (name) apply(name);
  };

  return (
    <section className="trading-watchlist" aria-label="Trading watchlists">
      <div className="trading-watchlist-controls">
        <select
          value={flagColor ? selectedListId : selected?.record_id ?? ''}
          onChange={(event) => {
            setSelectedListId(event.target.value);
            setFlagMenuFor(null);
          }}
          aria-label="Watchlist"
        >
          {records.map((record) => <option key={record.record_id} value={record.record_id}>{upgradeWatchlistPayload(record.payload).name}</option>)}
          {flagListColors.length ? (
            <optgroup label="Flagged lists">
              {flagListColors.map((color) => <option key={color} value={flagListId(color)}>{flagListName(color)}</option>)}
            </optgroup>
          ) : null}
        </select>
        <button
          type="button"
          onClick={() => setSymbolPickerOpen(true)}
          disabled={(!selected && !flagColor) || status === 'loading' || status === 'saving'}
          aria-label={`Add symbol to ${listName}`}
          title={`Add symbol to ${listName}`}
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
              <button type="button" role="menuitem" onClick={() => promptName('Section name', 'New section', (name) => commit(addWatchlistSection(current, name)))} disabled={!selected}>Add section</button>
              <button type="button" role="menuitem" onClick={() => promptName('Rename watchlist', current.name, (name) => void save({ ...current, name }))} disabled={!selected}>Rename watchlist</button>
              <button type="button" role="menuitem" onClick={() => { setOptionsOpen(false); void archive(); }} disabled={!selected || records.length <= 1}>Delete watchlist</button>
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
          aria-pressed={sorted}
          title={`Change over ${interval}. Click to sort.`}
          onClick={() => setChangeSort((value) => value === 'manual' ? 'desc' : value === 'desc' ? 'asc' : 'manual')}
        >
          <span>Chg%</span>
          <span aria-hidden="true">{changeSort === 'desc' ? '↓' : changeSort === 'asc' ? '↑' : '↕'}</span>
        </button>
      </div>
      <ul>
        {rows.map((row) => {
          const canMoveUp = row.itemIndex > 0;
          const canMoveDown = row.itemIndex < listItems.length - 1;
          const move = (direction: -1 | 1) => commit(moveWatchlistItem(current, row.itemIndex, direction));
          if (row.kind === 'section') {
            const { section } = row;
            return (
              <TradingWatchlistSectionRow
                key={`section:${section.id}`}
                section={section}
                symbolCount={row.symbolCount}
                sorted={sorted}
                canMoveUp={canMoveUp}
                canMoveDown={canMoveDown}
                onToggle={() => commit(updateWatchlistSection(current, section.id, { collapsed: !section.collapsed }))}
                onMove={move}
                onRename={() => promptName('Rename section', section.name, (name) => commit(updateWatchlistSection(current, section.id, { name })))}
                onRemove={() => commit(removeWatchlistSection(current, section.id))}
              />
            );
          }
          const { instrumentId } = row;
          const symbol = watchlistDisplaySymbol(instrumentById.get(instrumentId)?.display_symbol, instrumentId);
          return (
            <TradingWatchlistSymbolRow
              key={instrumentId}
              instrumentId={instrumentId}
              symbol={symbol}
              quote={quotes[instrumentId]}
              flag={flags.get(instrumentId)}
              active={instrumentId === normalizedActiveInstrumentId}
              sorted={sorted}
              movable={!flagColor}
              canMoveUp={canMoveUp}
              canMoveDown={canMoveDown}
              flagMenuOpen={flagMenuFor === instrumentId}
              removeTitle={flagColor ? 'Remove flag' : 'Remove'}
              onSelect={() => onSelect(binanceInstrumentIdFor(instrumentId))}
              onMove={move}
              onToggleFlagMenu={(open) => setFlagMenuFor(open ? instrumentId : null)}
              onPickFlag={(color) => {
                setFlagMenuFor(null);
                void setFlag([instrumentId], color);
              }}
              onRemove={() => removeInstrument(instrumentId)}
            />
          );
        })}
      </ul>
      <span className="trading-watchlist-status" aria-live="polite">{status}</span>
      <TradingWatchlistSymbolPicker
        open={symbolPickerOpen}
        instruments={catalogInstruments}
        selectedInstrumentIds={instrumentIds}
        busy={status === 'saving'}
        onAdd={addInstrument}
        onClose={() => setSymbolPickerOpen(false)}
      />
    </section>
  );
}
