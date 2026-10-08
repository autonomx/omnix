import { formatWatchlistPrice } from './tradingWatchlistPresentation';

/**
 * Watchlist columns (TVP-5.2). Every column reads one value from the symbol's
 * snapshot, so sorting works the same way for all of them.
 *
 * Extension point: indicator columns (TVP-5.2 after TVP-0.2) add definitions
 * whose `value` reads a server-side indicator result added to the snapshot;
 * the header, cells, sorting and the column chooser need no change.
 */
export type WatchlistSnapshot = {
  price: string | null;
  changePercent: number | null;
  change?: number | null;
  volume?: number | null;
  relativeVolume?: number | null;
  high?: number | null;
  low?: number | null;
  extendedPrice?: string | null;
};

export type WatchlistColumnId =
  | 'last'
  | 'change'
  | 'changePercent'
  | 'volume'
  | 'relativeVolume'
  | 'extendedPrice'
  | 'high'
  | 'low';

export type WatchlistColumnTone = 'positive' | 'negative' | 'neutral' | null;

export type WatchlistColumnDefinition = {
  id: WatchlistColumnId;
  /** Header text. */
  label: string;
  /** Used in the column chooser and in sort button labels. */
  description: string;
  /** Wide columns hold prices and volumes; narrow ones hold changes and ratios. */
  width: 'wide' | 'narrow';
  value: (snapshot: WatchlistSnapshot | undefined) => number | null;
  format: (snapshot: WatchlistSnapshot | undefined) => string;
  /** Colours the cell by sign (change columns). */
  signed?: boolean;
};

const EMPTY = '—';

function numeric(value: string | number | null | undefined): number | null {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatSigned(value: number | null, suffix = '', digits = 2): string {
  if (value == null) return EMPTY;
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`;
}

const VOLUME_FORMATTER = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 });

function formatPriceValue(value: number | null | undefined): string {
  return value == null ? EMPTY : formatWatchlistPrice(String(value));
}

export const WATCHLIST_COLUMNS: readonly WatchlistColumnDefinition[] = [
  {
    id: 'last',
    label: 'Last',
    description: 'last price',
    width: 'wide',
    value: (snapshot) => numeric(snapshot?.price),
    format: (snapshot) => formatWatchlistPrice(snapshot?.price),
  },
  {
    id: 'change',
    label: 'Chg',
    description: 'change',
    width: 'narrow',
    signed: true,
    value: (snapshot) => snapshot?.change ?? null,
    format: (snapshot) => formatSigned(snapshot?.change ?? null),
  },
  {
    id: 'changePercent',
    label: 'Chg%',
    description: 'change percentage',
    width: 'narrow',
    signed: true,
    value: (snapshot) => snapshot?.changePercent ?? null,
    format: (snapshot) => formatSigned(snapshot?.changePercent ?? null, '%'),
  },
  {
    id: 'volume',
    label: 'Vol',
    description: 'volume',
    width: 'wide',
    value: (snapshot) => snapshot?.volume ?? null,
    format: (snapshot) => snapshot?.volume == null ? EMPTY : VOLUME_FORMATTER.format(snapshot.volume),
  },
  {
    id: 'relativeVolume',
    label: 'Rel Vol',
    description: 'relative volume',
    width: 'narrow',
    value: (snapshot) => snapshot?.relativeVolume ?? null,
    format: (snapshot) => snapshot?.relativeVolume == null ? EMPTY : `${snapshot.relativeVolume.toFixed(2)}×`,
  },
  {
    id: 'extendedPrice',
    label: 'Ext',
    description: 'extended-hours price',
    width: 'wide',
    value: (snapshot) => numeric(snapshot?.extendedPrice),
    format: (snapshot) => snapshot?.extendedPrice ? formatWatchlistPrice(snapshot.extendedPrice) : EMPTY,
  },
  {
    id: 'high',
    label: 'High',
    description: 'high',
    width: 'wide',
    value: (snapshot) => snapshot?.high ?? null,
    format: (snapshot) => formatPriceValue(snapshot?.high),
  },
  {
    id: 'low',
    label: 'Low',
    description: 'low',
    width: 'wide',
    value: (snapshot) => snapshot?.low ?? null,
    format: (snapshot) => formatPriceValue(snapshot?.low),
  },
];

export const DEFAULT_WATCHLIST_COLUMNS: readonly WatchlistColumnId[] = ['last', 'changePercent'];

const COLUMN_BY_ID = new Map(WATCHLIST_COLUMNS.map((column) => [column.id, column]));

export function watchlistColumn(id: WatchlistColumnId): WatchlistColumnDefinition | undefined {
  return COLUMN_BY_ID.get(id);
}

export function columnTone(column: WatchlistColumnDefinition, snapshot: WatchlistSnapshot | undefined): WatchlistColumnTone {
  if (!column.signed) return null;
  const value = column.value(snapshot);
  if (value == null) return null;
  return value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral';
}

/** Chosen columns in the chooser's order; the symbol column is always shown. */
export function toggleWatchlistColumn(columns: readonly WatchlistColumnId[], id: WatchlistColumnId): WatchlistColumnId[] {
  const chosen = new Set(columns);
  if (chosen.has(id)) chosen.delete(id);
  else chosen.add(id);
  return WATCHLIST_COLUMNS.map((column) => column.id).filter((columnId) => chosen.has(columnId));
}

export type WatchlistSortKey = 'symbol' | WatchlistColumnId;
export type WatchlistSort = { key: WatchlistSortKey; direction: 'asc' | 'desc' } | null;

/** Values sort high to low first, symbols A to Z first; the third click restores the list order. */
export function nextWatchlistSort(current: WatchlistSort, key: WatchlistSortKey): WatchlistSort {
  const first = key === 'symbol' ? 'asc' : 'desc';
  if (current?.key !== key) return { key, direction: first };
  if (current.direction === first) return { key, direction: first === 'asc' ? 'desc' : 'asc' };
  return null;
}

/** Empty values always sort last; ties keep the list order (the caller's stable fallback). */
export function watchlistComparator(
  sort: WatchlistSort,
  snapshots: Readonly<Record<string, WatchlistSnapshot | undefined>>,
  symbolFor: (instrumentId: string) => string,
): ((left: string, right: string) => number) | undefined {
  if (!sort) return undefined;
  const sign = sort.direction === 'asc' ? 1 : -1;
  if (sort.key === 'symbol') {
    return (left, right) => sign * symbolFor(left).localeCompare(symbolFor(right));
  }
  const column = watchlistColumn(sort.key);
  if (!column) return undefined;
  return (left, right) => {
    const leftValue = column.value(snapshots[left]);
    const rightValue = column.value(snapshots[right]);
    if (leftValue == null && rightValue == null) return 0;
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    return sign * (leftValue - rightValue);
  };
}

/* The chosen columns and sort are a per-browser view preference. */

const VIEW_STORAGE_KEY = 'omnix.trading.watchlist-view';

export type WatchlistView = { columns: WatchlistColumnId[]; sort: WatchlistSort };

function isColumnId(value: unknown): value is WatchlistColumnId {
  return typeof value === 'string' && COLUMN_BY_ID.has(value as WatchlistColumnId);
}

export function readWatchlistView(): WatchlistView {
  const fallback: WatchlistView = { columns: [...DEFAULT_WATCHLIST_COLUMNS], sort: null };
  try {
    const stored = JSON.parse(window.localStorage.getItem(VIEW_STORAGE_KEY) ?? 'null') as Partial<WatchlistView> | null;
    if (!stored || typeof stored !== 'object') return fallback;
    const columns = Array.isArray(stored.columns) ? stored.columns.filter(isColumnId) : fallback.columns;
    const sort = stored.sort
      && (stored.sort.key === 'symbol' || isColumnId(stored.sort.key))
      && (stored.sort.direction === 'asc' || stored.sort.direction === 'desc')
      ? { key: stored.sort.key, direction: stored.sort.direction }
      : null;
    return { columns, sort };
  } catch {
    return fallback;
  }
}

export function writeWatchlistView(view: WatchlistView): void {
  try {
    window.localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify(view));
  } catch {
    // Storage can be unavailable (private mode); the view then lasts for the session.
  }
}
