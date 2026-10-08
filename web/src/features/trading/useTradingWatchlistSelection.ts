import { useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';

/**
 * Watchlist keyboard navigation and row selection (TVP-5.3).
 *
 * Keys are read by the watchlist's own key handler because Omnix has no
 * shared shortcut layer yet. `watchlistKeyCommand` maps a key to a named
 * command and `applyWatchlistCommand` is a pure state change, so moving these
 * bindings to the command layer (TVP-0.3) means registering the four commands
 * there and dropping the handler.
 */
export type WatchlistSelection = { ids: readonly string[]; cursor: string | null; anchor: string | null };
export type WatchlistKeyCommand = 'next' | 'previous' | 'extendNext' | 'extendPrevious' | 'selectAll';

type KeyLike = Pick<KeyboardEvent, 'key' | 'shiftKey' | 'ctrlKey' | 'metaKey' | 'altKey'>;

const EMPTY_SELECTION: WatchlistSelection = { ids: [], cursor: null, anchor: null };

export function watchlistKeyCommand(event: KeyLike): WatchlistKeyCommand | null {
  if (event.altKey) return null;
  if (event.ctrlKey || event.metaKey) {
    return !event.shiftKey && event.key.toLowerCase() === 'a' ? 'selectAll' : null;
  }
  switch (event.key) {
    case 'ArrowDown':
      return event.shiftKey ? 'extendNext' : 'next';
    case 'ArrowUp':
      return event.shiftKey ? 'extendPrevious' : 'previous';
    case ' ':
    case 'Spacebar':
      return event.shiftKey ? 'previous' : 'next';
    default:
      return null;
  }
}

/**
 * Keys typed into a field, an open menu or a row's action buttons (marked
 * `data-watchlist-keys="own"`) belong to that control, so Space still
 * presses a focused action button.
 */
export function isWatchlistKeyTargetIgnored(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable
    || target.tagName === 'INPUT'
    || target.tagName === 'TEXTAREA'
    || target.tagName === 'SELECT'
    || target.closest('[role="menu"], [data-watchlist-keys="own"]') != null;
}

function rangeIds(order: readonly string[], from: string, to: string): string[] {
  const [start, end] = [order.indexOf(from), order.indexOf(to)].sort((left, right) => left - right);
  return order.slice(start, end + 1);
}

/**
 * Apply a command to the selection over the visible symbols in `order`.
 * Moving starts from the cursor, else from `startFrom` (the chart's symbol).
 * `show` is the symbol to open on the chart, if any.
 */
export function applyWatchlistCommand(
  selection: WatchlistSelection,
  order: readonly string[],
  command: WatchlistKeyCommand,
  startFrom?: string | null,
): { selection: WatchlistSelection; show: string | null } {
  if (order.length === 0) return { selection, show: null };
  const cursor = selection.cursor && order.includes(selection.cursor) ? selection.cursor : null;
  if (command === 'selectAll') {
    const target = cursor ?? order[0];
    return { selection: { ids: [...order], cursor: target, anchor: target }, show: null };
  }
  const start = cursor ?? (startFrom && order.includes(startFrom) ? startFrom : null);
  const step = command === 'next' || command === 'extendNext' ? 1 : -1;
  const index = start == null ? -1 : order.indexOf(start);
  const nextIndex = index < 0
    ? (step > 0 ? 0 : order.length - 1)
    : Math.min(order.length - 1, Math.max(0, index + step));
  const next = order[nextIndex];
  if (command === 'next' || command === 'previous') {
    return { selection: { ids: [next], cursor: next, anchor: next }, show: next };
  }
  const anchor = selection.anchor && order.includes(selection.anchor) ? selection.anchor : start ?? next;
  return { selection: { ids: rangeIds(order, anchor, next), cursor: next, anchor }, show: null };
}

/** A row click: plain selects and shows, Shift extends, Ctrl/Cmd toggles. */
export function clickWatchlistRow(
  selection: WatchlistSelection,
  order: readonly string[],
  instrumentId: string,
  modifiers: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean },
): { selection: WatchlistSelection; show: string | null } {
  if (modifiers.shiftKey && selection.anchor && order.includes(selection.anchor)) {
    return { selection: { ids: rangeIds(order, selection.anchor, instrumentId), cursor: instrumentId, anchor: selection.anchor }, show: null };
  }
  if (modifiers.ctrlKey || modifiers.metaKey) {
    const ids = selection.ids.includes(instrumentId)
      ? selection.ids.filter((id) => id !== instrumentId)
      : [...selection.ids, instrumentId];
    return { selection: { ids, cursor: instrumentId, anchor: instrumentId }, show: null };
  }
  return { selection: { ids: [instrumentId], cursor: instrumentId, anchor: instrumentId }, show: instrumentId };
}

export function useTradingWatchlistSelection(
  order: readonly string[],
  activeInstrumentId: string,
  onShow: (instrumentId: string) => void,
) {
  const [selection, setSelection] = useState<WatchlistSelection>(EMPTY_SELECTION);
  const listRef = useRef<HTMLUListElement>(null);
  const selectedIds = useMemo(
    () => new Set(selection.ids.filter((id) => order.includes(id))),
    [order, selection.ids],
  );

  const apply = (result: { selection: WatchlistSelection; show: string | null }) => {
    setSelection(result.selection);
    if (result.show) onShow(result.show);
    const cursor = result.selection.cursor;
    const row = [...(listRef.current?.querySelectorAll<HTMLElement>('[data-instrument-id]') ?? [])]
      .find((element) => element.dataset.instrumentId === cursor);
    row?.scrollIntoView?.({ block: 'nearest' });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (isWatchlistKeyTargetIgnored(event.target)) return;
    const command = watchlistKeyCommand(event);
    if (!command) return;
    event.preventDefault();
    apply(applyWatchlistCommand(selection, order, command, activeInstrumentId));
  };

  const onRowClick = (instrumentId: string, event: MouseEvent) => {
    apply(clickWatchlistRow(selection, order, instrumentId, event));
  };

  return { selectedIds, cursor: selection.cursor, listRef, onKeyDown, onRowClick };
}
