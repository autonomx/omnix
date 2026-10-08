import { TradingWatchlistLogo } from './TradingWatchlistLogo';
import { formatWatchlistPrice } from './tradingWatchlistPresentation';
import {
  WATCHLIST_FLAG_COLORS,
  WATCHLIST_FLAG_LABELS,
  type WatchlistFlagColor,
  type WatchlistSectionItem,
} from './tradingWatchlistModel';
import type { WatchlistQuoteSnapshot } from './useTradingWatchlistQuotes';

function formatChange(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
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
      <span className={`trading-watchlist-row-actions${sorted ? ' is-sorted' : ''}`}>
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
  flag,
  active,
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
  flag: WatchlistFlagColor | undefined;
  active: boolean;
  sorted: boolean;
  /** False in a generated flag list, which has no manual order. */
  movable: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  flagMenuOpen: boolean;
  removeTitle: string;
  onSelect: () => void;
  onMove: (direction: -1 | 1) => void;
  onToggleFlagMenu: (open: boolean) => void;
  onPickFlag: (color: WatchlistFlagColor | null) => void;
  onRemove: () => void;
}) {
  const changePercent = quote?.changePercent;
  const tone = changePercent == null ? '' : changePercent > 0 ? ' positive' : changePercent < 0 ? ' negative' : ' neutral';
  return (
    <li className={active ? 'active' : undefined}>
      <button type="button" onClick={onSelect} aria-label={`Select ${symbol}`}>
        {flag ? (
          <span className={`trading-watchlist-flag ${flag}`} role="img" aria-label={`${WATCHLIST_FLAG_LABELS[flag]} flag`} title={`${WATCHLIST_FLAG_LABELS[flag]} flag`} />
        ) : null}
        <TradingWatchlistLogo symbol={symbol} instrumentId={instrumentId} />
        <strong>{symbol}</strong>
      </button>
      <span className="trading-watchlist-price">{formatWatchlistPrice(quote?.price)}</span>
      <span className={`trading-watchlist-change${tone}`}>{formatChange(changePercent)}</span>
      <span className={`trading-watchlist-row-actions${sorted ? ' is-sorted' : ''}`}>
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
