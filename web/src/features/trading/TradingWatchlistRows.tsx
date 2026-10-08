import type { MouseEvent } from 'react';
import { TradingWatchlistLogo } from './TradingWatchlistLogo';
import {
  columnTone,
  nextWatchlistSort,
  type WatchlistColumnDefinition,
  type WatchlistSort,
  type WatchlistSortKey,
} from './tradingWatchlistColumns';
import {
  WATCHLIST_FLAG_COLORS,
  WATCHLIST_FLAG_LABELS,
  type WatchlistFlagColor,
  type WatchlistSectionItem,
} from './tradingWatchlistModel';
import type { WatchlistQuoteSnapshot } from './useTradingWatchlistQuotes';

function sortLabel(sort: WatchlistSort, key: WatchlistSortKey, description: string): string {
  const next = nextWatchlistSort(sort, key);
  return next
    ? `Sort watchlist by ${description} ${next.direction === 'asc' ? 'ascending' : 'descending'}`
    : `Clear watchlist ${description} sort`;
}

/**
 * The header row of the watchlist grid; each column header sorts the list by
 * its column and reports the current order with `aria-sort`.
 */
export function TradingWatchlistHeader({
  columns,
  sort,
  interval,
  onSort,
}: {
  columns: readonly WatchlistColumnDefinition[];
  sort: WatchlistSort;
  interval: string;
  onSort: (key: WatchlistSortKey) => void;
}) {
  const header = (key: WatchlistSortKey, label: string, description: string, title: string) => {
    const direction = sort?.key === key ? sort.direction : null;
    return (
      <div
        key={key}
        role="columnheader"
        className={`trading-watchlist-header-cell${key === 'symbol' ? ' symbol' : ''}`}
        aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'}
      >
        <button
          type="button"
          className="trading-watchlist-sort"
          aria-label={sortLabel(sort, key, description)}
          title={title}
          onClick={() => onSort(key)}
        >
          <span>{label}</span>
          <span aria-hidden="true">{direction === 'desc' ? '↓' : direction === 'asc' ? '↑' : '↕'}</span>
        </button>
      </div>
    );
  };
  return (
    <div className="trading-watchlist-columns" role="row">
      {header('symbol', 'Symbol', 'symbol', 'Click to sort by symbol.')}
      {columns.map((column) => header(
        column.id,
        column.label,
        column.description,
        `${column.hint ?? column.label}${column.signed ? ` over ${interval}` : ''}. Click to sort.`,
      ))}
    </div>
  );
}

function TradingWatchlistFlagMenu({
  symbol,
  current,
  onPick,
  onClose,
}: {
  symbol: string;
  current: WatchlistFlagColor | undefined;
  onPick: (color: WatchlistFlagColor | null) => void;
  onClose: () => void;
}) {
  return (
    <div
      className="trading-watchlist-flag-menu"
      role="menu"
      aria-label={`Flag ${symbol}`}
      onKeyDown={(event) => {
        if (event.key !== 'Escape') return;
        event.stopPropagation();
        onClose();
      }}
    >
      {WATCHLIST_FLAG_COLORS.map((color) => (
        <button
          key={color}
          type="button"
          role="menuitemradio"
          aria-checked={current === color}
          aria-label={`${WATCHLIST_FLAG_LABELS[color]} flag`}
          title={`${WATCHLIST_FLAG_LABELS[color]} flag`}
          onClick={() => onPick(color)}
        >
          <span className={`trading-watchlist-flag-swatch ${color}`} aria-hidden="true" />
        </button>
      ))}
      <button type="button" role="menuitem" className="trading-watchlist-flag-clear" onClick={() => onPick(null)} disabled={!current}>
        Remove flag
      </button>
    </div>
  );
}

export function TradingWatchlistSectionRow({
  section,
  symbolCount,
  sorted,
  canMoveUp,
  canMoveDown,
  onToggle,
  onMove,
  onRename,
  onRemove,
}: {
  section: WatchlistSectionItem;
  symbolCount: number;
  sorted: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onToggle: () => void;
  onMove: (direction: -1 | 1) => void;
  onRename: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="trading-watchlist-section" role="row">
      <div role="gridcell" className="trading-watchlist-section-cell">
        <button
          type="button"
          className="trading-watchlist-section-toggle"
          aria-expanded={!section.collapsed}
          aria-label={`${section.collapsed ? 'Expand' : 'Collapse'} section ${section.name}`}
          onClick={onToggle}
        >
          <span className="trading-watchlist-section-chevron" aria-hidden="true">{section.collapsed ? '▸' : '▾'}</span>
          <strong>{section.name}</strong>
          <small>{symbolCount}</small>
        </button>
      </div>
      <span role="gridcell" className={`trading-watchlist-row-actions${sorted ? ' is-sorted' : ''}`} data-watchlist-keys="own">
        <button type="button" onClick={() => onMove(-1)} disabled={!canMoveUp} aria-label={`Move section ${section.name} up`} title="Move up">↑</button>
        <button type="button" onClick={() => onMove(1)} disabled={!canMoveDown} aria-label={`Move section ${section.name} down`} title="Move down">↓</button>
        <button type="button" onClick={onRename} aria-label={`Rename section ${section.name}`} title="Rename section">✎</button>
        <button type="button" onClick={onRemove} aria-label={`Remove section ${section.name}`} title="Remove section (keeps its symbols)">×</button>
      </span>
    </li>
  );
}

export function TradingWatchlistSymbolRow({
  rowId,
  instrumentId,
  symbol,
  quote,
  columns,
  flag,
  active,
  selected,
  sorted,
  movable,
  removable,
  canMoveUp,
  canMoveDown,
  flagMenuOpen,
  removeTitle,
  onSelect,
  onMove,
  onToggleFlagMenu,
  onPickFlag,
  onRemove,
}: {
  /** Element id, referenced by the grid's `aria-activedescendant`. */
  rowId: string;
  instrumentId: string;
  symbol: string;
  quote: WatchlistQuoteSnapshot | undefined;
  columns: readonly WatchlistColumnDefinition[];
  flag: WatchlistFlagColor | undefined;
  active: boolean;
  /** Part of the keyboard or mouse selection. */
  selected: boolean;
  sorted: boolean;
  /** False in a generated flag list, which has no manual order. */
  movable: boolean;
  /** False for a read-only list (saved by a newer Omnix). */
  removable: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  flagMenuOpen: boolean;
  removeTitle: string;
  onSelect: (event: MouseEvent) => void;
  onMove: (direction: -1 | 1) => void;
  onToggleFlagMenu: (open: boolean) => void;
  onPickFlag: (color: WatchlistFlagColor | null) => void;
  onRemove: () => void;
}) {
  return (
    <li
      id={rowId}
      role="row"
      aria-selected={selected}
      className={[active ? 'active' : '', selected ? 'selected' : ''].join(' ').trim() || undefined}
      data-instrument-id={instrumentId}
    >
      <div role="gridcell" className="trading-watchlist-symbol-cell">
        <button type="button" onClick={onSelect} aria-label={`Select ${symbol}`}>
          {flag ? (
            <span className={`trading-watchlist-flag ${flag}`} role="img" aria-label={`${WATCHLIST_FLAG_LABELS[flag]} flag`} title={`${WATCHLIST_FLAG_LABELS[flag]} flag`} />
          ) : null}
          <TradingWatchlistLogo symbol={symbol} instrumentId={instrumentId} />
          <strong>{symbol}</strong>
        </button>
        {flagMenuOpen ? (
          <TradingWatchlistFlagMenu symbol={symbol} current={flag} onPick={onPickFlag} onClose={() => onToggleFlagMenu(false)} />
        ) : null}
      </div>
      {columns.map((column) => {
        const tone = columnTone(column, quote);
        return (
          <span key={column.id} role="gridcell" className={column.signed ? `trading-watchlist-change${tone ? ` ${tone}` : ''}` : 'trading-watchlist-price'}>
            {column.format(quote)}
          </span>
        );
      })}
      <span role="gridcell" className={`trading-watchlist-row-actions${sorted ? ' is-sorted' : ''}`} data-watchlist-keys="own">
        {movable ? (
          <>
            <button type="button" onClick={() => onMove(-1)} disabled={!canMoveUp} aria-label={`Move ${symbol} up`} title="Move up">↑</button>
            <button type="button" onClick={() => onMove(1)} disabled={!canMoveDown} aria-label={`Move ${symbol} down`} title="Move down">↓</button>
          </>
        ) : null}
        <button
          type="button"
          onClick={() => onToggleFlagMenu(!flagMenuOpen)}
          aria-label={`Flag ${symbol}`}
          aria-haspopup="menu"
          aria-expanded={flagMenuOpen}
          title="Flag"
        >
          ⚑
        </button>
        {removable ? <button type="button" onClick={onRemove} aria-label={`Remove ${symbol}`} title={removeTitle}>×</button> : null}
      </span>
    </li>
  );
}
