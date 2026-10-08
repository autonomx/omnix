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

/** Column headers; each one sorts the list by its column. */
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
      <button
        key={key}
        type="button"
        className={`trading-watchlist-sort${key === 'symbol' ? ' symbol' : ''}`}
        aria-label={sortLabel(sort, key, description)}
        aria-pressed={direction != null}
        title={title}
        onClick={() => onSort(key)}
      >
        <span>{label}</span>
        <span aria-hidden="true">{direction === 'desc' ? '↓' : direction === 'asc' ? '↑' : '↕'}</span>
      </button>
    );
  };
  return (
    <div className="trading-watchlist-columns">
      {header('symbol', 'Symbol', 'symbol', 'Click to sort by symbol.')}
      {columns.map((column) => header(
        column.id,
        column.label,
        column.description,
        column.signed ? `${column.label} over ${interval}. Click to sort.` : `${column.label}. Click to sort.`,
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
    <li className="trading-watchlist-section">
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
      <span className={`trading-watchlist-row-actions${sorted ? ' is-sorted' : ''}`} data-watchlist-keys="own">
        <button type="button" onClick={() => onMove(-1)} disabled={!canMoveUp} aria-label={`Move section ${section.name} up`} title="Move up">↑</button>
        <button type="button" onClick={() => onMove(1)} disabled={!canMoveDown} aria-label={`Move section ${section.name} down`} title="Move down">↓</button>
        <button type="button" onClick={onRename} aria-label={`Rename section ${section.name}`} title="Rename section">✎</button>
        <button type="button" onClick={onRemove} aria-label={`Remove section ${section.name}`} title="Remove section (keeps its symbols)">×</button>
      </span>
    </li>
  );
}

export function TradingWatchlistSymbolRow({
  instrumentId,
  symbol,
  quote,
  columns,
  flag,
  active,
  selected,
  sorted,
  movable,
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
    <li className={[active ? 'active' : '', selected ? 'selected' : ''].join(' ').trim() || undefined} data-instrument-id={instrumentId}>
      <button type="button" onClick={onSelect} aria-label={`Select ${symbol}`}>
        {flag ? (
          <span className={`trading-watchlist-flag ${flag}`} role="img" aria-label={`${WATCHLIST_FLAG_LABELS[flag]} flag`} title={`${WATCHLIST_FLAG_LABELS[flag]} flag`} />
        ) : null}
        <TradingWatchlistLogo symbol={symbol} instrumentId={instrumentId} />
        <strong>{symbol}</strong>
      </button>
      {columns.map((column) => {
        const tone = columnTone(column, quote);
        return (
          <span key={column.id} className={column.signed ? `trading-watchlist-change${tone ? ` ${tone}` : ''}` : 'trading-watchlist-price'}>
            {column.format(quote)}
          </span>
        );
      })}
      <span className={`trading-watchlist-row-actions${sorted ? ' is-sorted' : ''}`} data-watchlist-keys="own">
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
        <button type="button" onClick={onRemove} aria-label={`Remove ${symbol}`} title={removeTitle}>×</button>
      </span>
      {flagMenuOpen ? (
        <TradingWatchlistFlagMenu symbol={symbol} current={flag} onPick={onPickFlag} onClose={() => onToggleFlagMenu(false)} />
      ) : null}
    </li>
  );
}
