import { useCallback, useId, useMemo, useState, type CSSProperties } from 'react';
import { binanceInstrumentIdFor } from './cryptoInstrumentDefaults';
import type { CanonicalInstrument, ProviderBinding } from './tradingTypes';
import { watchlistDisplaySymbol } from './tradingWatchlistPresentation';
import { watchlistComparator, type WatchlistColumnDefinition } from './tradingWatchlistColumns';
import { useTradingWatchlistView } from './useTradingWatchlistView';
import {
  WATCHLIST_FLAG_COLORS,
  WATCHLIST_FLAG_LABELS,
  addWatchlistSection,
  addWatchlistSymbols,
  flagListId,
  flaggedInstrumentIds,
  isSymbolItem,
  moveWatchlistEntry,
  newWatchlistSectionId,
  removeWatchlistSection,
  removeWatchlistSymbols,
  updateWatchlistSection,
  upgradeWatchlistPayload,
  watchlistRows,
  watchlistSymbolIds,
  type WatchlistFlagColor,
  type WatchlistItem,
} from './tradingWatchlistModel';
import { useTradingWatchlistDocuments } from './useTradingWatchlistDocuments';
import { useTradingWatchlistFlags } from './useTradingWatchlistFlags';
import { useTradingWatchlistQuotes } from './useTradingWatchlistQuotes';
import { useTradingWatchlistSelection } from './useTradingWatchlistSelection';
import { downloadWatchlistText, exchangeSymbolFor, formatWatchlistText } from './tradingWatchlistTransfer';
import { useTradingWatchlistImport } from './useTradingWatchlistImport';
import { TradingWatchlistOptionsMenu } from './TradingWatchlistOptionsMenu';
import { TradingWatchlistHeader, TradingWatchlistSectionRow, TradingWatchlistSymbolRow } from './TradingWatchlistRows';
import { TradingWatchlistSymbolPicker } from './TradingWatchlistSymbolPicker';
import './TradingWatchlist.css';

function mergeInstruments(
  current: readonly CanonicalInstrument[],
  next: CanonicalInstrument,
): CanonicalInstrument[] {
  return [...new Map([...current, next].map((instrument) => [instrument.instrument_id, instrument])).values()];
}

function flagListName(color: WatchlistFlagColor): string {
  return `${WATCHLIST_FLAG_LABELS[color]} flags`;
}

/** Symbol column plus one track per chosen column (see `.trading-watchlist` in the CSS). */
function gridStyle(columns: readonly WatchlistColumnDefinition[]): CSSProperties {
  const tracks = columns.map((column) => `var(--trading-watchlist-${column.width}-column)`);
  return { '--trading-watchlist-grid': ['minmax(0, 1fr)', ...tracks].join(' ') } as CSSProperties;
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
    records, selectedListId, setSelectedListId, flagColor, selected, current, readOnly, status, commit, create, archive,
  } = useTradingWatchlistDocuments(instruments);
  const { payload: flagsPayload, flags, setFlag } = useTradingWatchlistFlags();
  const view = useTradingWatchlistView();
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
  const { columns } = view;
  const quotes = useTradingWatchlistQuotes(instrumentIds, interval, providerBindings, view.columnIds.includes('relativeVolume'));
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

  const symbolFor = useCallback(
    (instrumentId: string) => watchlistDisplaySymbol(instrumentById.get(instrumentId)?.display_symbol, instrumentId),
    [instrumentById],
  );
  const rows = useMemo(
    () => watchlistRows(listItems, watchlistComparator(view.sort, quotes, symbolFor)),
    [listItems, quotes, symbolFor, view.sort],
  );
  const sorted = view.sort != null;
  const knownInstrumentIds = useMemo(
    () => new Set(records.flatMap((record) => watchlistSymbolIds(upgradeWatchlistPayload(record.payload)))),
    [records],
  );
  const importer = useTradingWatchlistImport({
    catalog: catalogInstruments,
    preferredInstrumentIds: knownInstrumentIds,
    create,
    onInstrumentsFound: (found) => setDiscoveredInstruments((items) => found.reduce(mergeInstruments, items)),
  });
  const visibleOrder = useMemo(() => rows.flatMap((row) => row.kind === 'symbol' ? [row.instrumentId] : []), [rows]);
  const { selectedIds, cursor, listRef, onKeyDown, onRowClick } = useTradingWatchlistSelection(
    visibleOrder,
    normalizedActiveInstrumentId,
    (instrumentId) => onSelect(binanceInstrumentIdFor(instrumentId)),
  );
  const listName = flagColor ? flagListName(flagColor).toLowerCase() : 'watchlist';
  const editable = !flagColor && !readOnly;
  const sectionIds = listItems.flatMap((item) => item.type === 'section' ? [item.id] : []);
  const rowIdPrefix = useId();
  const rowId = (instrumentId: string) => `${rowIdPrefix}row-${instrumentId}`;

  const addInstrument = async (instrument: CanonicalInstrument) => {
    const instrumentId = binanceInstrumentIdFor(instrument.instrument_id);
    setDiscoveredInstruments((items) => mergeInstruments(items, instrument));
    if (flagColor) {
      await setFlag([instrumentId], flagColor);
      return;
    }
    if (!selected || instrumentIds.includes(instrumentId)) return;
    commit((payload) => addWatchlistSymbols(payload, [instrumentId]));
  };

  const removeInstrument = (instrumentId: string) => {
    if (flagColor) void setFlag([instrumentId], null);
    else commit((payload) => removeWatchlistSymbols(payload, new Set([instrumentId])));
  };

  const promptName = (title: string, initial: string, apply: (name: string) => void) => {
    setOptionsOpen(false);
    const name = window.prompt(title, initial)?.trim();
    if (name) apply(name);
  };

  const exportList = () => {
    setOptionsOpen(false);
    downloadWatchlistText(
      flagColor ? flagListName(flagColor) : current.name,
      formatWatchlistText(listItems, (instrumentId) => exchangeSymbolFor(instrumentId, instrumentById.get(instrumentId))),
    );
  };

  const pickFlag = (instrumentId: string, color: WatchlistFlagColor | null) => {
    setFlagMenuFor(null);
    // A flag picked on a row of a multi-row selection applies to the whole selection.
    void setFlag(selectedIds.has(instrumentId) ? [...selectedIds] : [instrumentId], color);
  };

  return (
    <section className="trading-watchlist" aria-label="Trading watchlists" style={gridStyle(columns)}>
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
          disabled={(!selected && !flagColor) || readOnly || status === 'loading' || status === 'saving'}
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
            <TradingWatchlistOptionsMenu
              canEdit={selected != null && !readOnly}
              canDelete={selected != null && records.length > 1}
              columns={view.columnIds}
              onCreate={() => { setOptionsOpen(false); void create(); }}
              onAddSection={() => promptName('Section name', 'New section', (name) => {
                // The id is chosen once, so a retried save adds the same section.
                const id = newWatchlistSectionId();
                commit((payload) => addWatchlistSection(payload, name, cursor, id));
              })}
              onRename={() => promptName('Rename watchlist', current.name, (name) => commit((payload) => ({ ...payload, name })))}
              onDelete={() => { setOptionsOpen(false); void archive(); }}
              onImport={() => { setOptionsOpen(false); importer.openFilePicker(); }}
              onExport={exportList}
              onToggleColumn={view.toggleColumn}
            />
          ) : null}
        </div>
      </div>
      <div
        ref={listRef}
        className="trading-watchlist-table"
        role="grid"
        aria-label="Watchlist symbols"
        aria-multiselectable="true"
        aria-activedescendant={cursor ? rowId(cursor) : undefined}
        tabIndex={0}
        onKeyDown={onKeyDown}
      >
        <TradingWatchlistHeader
          columns={columns}
          sort={view.sort}
          interval={interval}
          onSort={view.sortBy}
        />
        <ul role="rowgroup">
          {rows.map((row) => {
            if (row.kind === 'section') {
              const { section } = row;
              const position = sectionIds.indexOf(section.id);
              return (
                <TradingWatchlistSectionRow
                  key={`section:${section.id}`}
                  section={section}
                  symbolCount={row.symbolCount}
                  sorted={sorted}
                  canMoveUp={position > 0}
                  canMoveDown={position < sectionIds.length - 1}
                  onToggle={() => commit((payload) => updateWatchlistSection(payload, section.id, { collapsed: !section.collapsed }))}
                  onMove={(direction) => commit((payload) => moveWatchlistEntry(payload, { type: 'section', id: section.id }, direction))}
                  onRename={() => promptName('Rename section', section.name, (name) => commit((payload) => updateWatchlistSection(payload, section.id, { name })))}
                  onRemove={() => commit((payload) => removeWatchlistSection(payload, section.id))}
                />
              );
            }
            const { instrumentId } = row;
            const symbol = symbolFor(instrumentId);
            return (
              <TradingWatchlistSymbolRow
                key={instrumentId}
                rowId={rowId(instrumentId)}
                instrumentId={instrumentId}
                symbol={symbol}
                quote={quotes[instrumentId]}
                columns={columns}
                flag={flags.get(instrumentId)}
                active={instrumentId === normalizedActiveInstrumentId}
                selected={selectedIds.has(instrumentId)}
                sorted={sorted}
                movable={editable}
                removable={!readOnly}
                canMoveUp={row.itemIndex > 0}
                canMoveDown={row.itemIndex < listItems.length - 1}
                flagMenuOpen={flagMenuFor === instrumentId}
                removeTitle={flagColor ? 'Remove flag' : 'Remove'}
                onSelect={(event) => onRowClick(instrumentId, event)}
                onMove={(direction) => commit((payload) => moveWatchlistEntry(payload, { type: 'symbol', instrumentId }, direction))}
                onToggleFlagMenu={(open) => setFlagMenuFor(open ? instrumentId : null)}
                onPickFlag={(color) => pickFlag(instrumentId, color)}
                onRemove={() => removeInstrument(instrumentId)}
              />
            );
          })}
        </ul>
      </div>
      {readOnly ? <p className="trading-watchlist-notice" role="status">This watchlist was saved by a newer version of Omnix and is read-only here.</p> : null}
      {importer.notice ? <p className="trading-watchlist-notice" role="status">{importer.notice}</p> : null}
      <span className="trading-watchlist-status" aria-live="polite">{status}</span>
      <input ref={importer.inputRef} type="file" accept=".txt,text/plain" hidden aria-label="Import watchlist file" onChange={importer.onInputChange} />
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
