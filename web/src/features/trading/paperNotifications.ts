// Paper trading notifications (TVP-7.4): fills, rejections, cancellations
// and expiries noticed between account snapshots, shown as a toast over the
// chart and kept in the terminal dock's Notifications tab. The first snapshot
// of an account only sets the baseline, so opening Omnix replays nothing.
import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { PaperAccountSnapshot, PaperOrder } from './paperTypes';

export type PaperNotificationKind = 'fill' | 'reject' | 'cancel' | 'expire';
export type PaperNotification = { id: string; at: string; kind: PaperNotificationKind; orderId: string; message: string };

const LOG_LIMIT = 200;
let log: readonly PaperNotification[] = [];
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function pushPaperNotifications(items: readonly PaperNotification[]): void {
  if (items.length === 0) return;
  log = [...items.slice().reverse(), ...log].slice(0, LOG_LIMIT);
  emit();
}

export function clearPaperNotifications(): void {
  log = [];
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The notifications log, newest first. */
export function usePaperNotifications(): readonly PaperNotification[] {
  return useSyncExternalStore(subscribe, () => log, () => log);
}

function symbolOf(instrumentId: string): string {
  return instrumentId.split(':').at(-1)?.replace('-', '/') ?? instrumentId;
}

function describe(order: PaperOrder): Omit<PaperNotification, 'id' | 'at' | 'orderId'> | null {
  const what = `${order.side === 'buy' ? 'Buy' : 'Sell'} ${order.quantity} ${symbolOf(order.instrument_id)} ${order.order_type.replace('_', ' ').toUpperCase()}`;
  switch (order.status) {
    case 'filled':
      return { kind: 'fill', message: `${what} filled${order.average_fill_price ? ` at ${order.average_fill_price}` : ''}` };
    case 'rejected':
      return { kind: 'reject', message: `${what} rejected${order.rejection_reason ? `: ${order.rejection_reason.replace(/_/g, ' ')}` : ''}` };
    case 'cancelled':
      return { kind: 'cancel', message: `${what} cancelled` };
    case 'expired':
      return { kind: 'expire', message: `${what} expired` };
    default:
      return null;
  }
}

function ordersOf(snapshot: PaperAccountSnapshot): PaperOrder[] {
  const byId = new Map<string, PaperOrder>();
  for (const order of [...(snapshot.order_history ?? []), ...(snapshot.open_orders ?? [])]) byId.set(order.order_id, order);
  return [...byId.values()];
}

/**
 * The notifications for orders whose status changed from `before` to `after` (or that appear already closed in
 * `after`). Orders that stay open, or keep their status, notify nothing.
 */
export function orderNotifications(before: PaperAccountSnapshot, after: PaperAccountSnapshot, now = new Date().toISOString()): PaperNotification[] {
  const previous = new Map(ordersOf(before).map((order) => [order.order_id, order.status]));
  return ordersOf(after).flatMap((order) => {
    if (previous.get(order.order_id) === order.status) return [];
    const described = describe(order);
    return described ? [{ id: `${order.order_id}:${order.status}`, at: order.updated_at ?? now, orderId: order.order_id, ...described }] : [];
  });
}

/** Watches an account's snapshots and logs what changed; a new account starts a new baseline. */
export function usePaperOrderNotifications(snapshot: PaperAccountSnapshot | null): void {
  const previous = useRef<PaperAccountSnapshot | null>(null);
  useEffect(() => {
    if (!snapshot) return;
    const before = previous.current;
    previous.current = snapshot;
    if (!before || before.account.account_id !== snapshot.account.account_id) return;
    pushPaperNotifications(orderNotifications(before, snapshot));
  }, [snapshot]);
}
