// Orders pre-filled from drawings (TVP-3.6): a long or short position's
// "Create buy/sell order" action sends an `order-ticket` request on the drawing
// action bus. The workspace opens the paper panel and leaves the pre-fill here;
// the panel takes it, fills the ticket and the user confirms. Nothing is placed
// without the panel's own confirmation.
import { useEffect, useRef } from 'react';
import { onDrawingActionRequest } from './drawings/drawingActions';

export type PaperTicketPrefill = {
  instrumentId: string;
  side: 'buy' | 'sell';
  entry: number;
  stop: number | null;
  target: number | null;
  quantity: number | null;
};

const positive = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null);

/** The request's payload as a pre-fill, or null when it is not one (the bus carries anything). */
export function parsePaperTicketRequest(payload: unknown): PaperTicketPrefill | null {
  if (!payload || typeof payload !== 'object') return null;
  const value = payload as Record<string, unknown>;
  const entry = positive(value.entry);
  if (typeof value.instrumentId !== 'string' || !value.instrumentId || (value.side !== 'buy' && value.side !== 'sell') || entry === null) return null;
  return { instrumentId: value.instrumentId, side: value.side, entry, stop: positive(value.stop), target: positive(value.target), quantity: positive(value.quantity) };
}

/** A pre-fill the panel doesn't take within this long is dropped: it never fills a ticket much later. */
export const PREFILL_LIFETIME_MS = 10_000;

let pending: { prefill: PaperTicketPrefill; at: number } | null = null;
const listeners = new Set<() => void>();

export function requestPaperTicket(prefill: PaperTicketPrefill, now = Date.now()): void {
  pending = { prefill, at: now };
  for (const listener of listeners) listener();
}

/** Takes the pending pre-fill (once), unless it is older than `PREFILL_LIFETIME_MS`. */
export function takePaperTicketPrefill(now = Date.now()): PaperTicketPrefill | null {
  const taken = pending;
  pending = null;
  return taken && now - taken.at <= PREFILL_LIFETIME_MS ? taken.prefill : null;
}

export function onPaperTicketRequest(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Workspace side: handles `order-ticket` requests by opening the paper panel with the pre-fill. */
export function usePaperTicketRequests(openPaperPanel: () => void): void {
  const open = useRef(openPaperPanel);
  useEffect(() => {
    open.current = openPaperPanel;
  });
  useEffect(() => onDrawingActionRequest('order-ticket', (payload) => {
    const prefill = parsePaperTicketRequest(payload);
    if (!prefill) return;
    requestPaperTicket(prefill);
    open.current();
  }), []);
}

/** The ticket fields a pre-fill sets. */
export type PaperTicketForm = {
  setTicketTab: (tab: 'order') => void;
  setSide: (side: 'buy' | 'sell') => void;
  setOrderType: (type: 'limit') => void;
  /** A limit order's price (the panel's "Limit price" field). */
  setTriggerPrice: (value: string) => void;
  /** Only a stop-limit's second price; cleared. */
  setLimitPrice: (value: string) => void;
  setStopLossEnabled: (enabled: boolean) => void;
  setStopLoss: (value: string) => void;
  setTakeProfitEnabled: (enabled: boolean) => void;
  setTakeProfit: (value: string) => void;
  setQuantity: (value: string) => void;
};

/** How the panel will place this order: a risk-managed entry carries stop and target and sizes the quantity itself. */
export type PaperTicketMode = { riskManaged: boolean; riskPercent: string };

/**
 * Fills the ticket from a pre-fill: a limit order at the entry. A risk-managed entry (a buy outside replay) also
 * gets the stop and target, and the account's risk rule sizes it; any other order gets the drawing's quantity and
 * no protection, since the panel can't send it, and the notice says so. Returns the notice to show; a drawing on
 * another symbol fills nothing.
 */
export function applyPaperTicketPrefill(
  prefill: PaperTicketPrefill,
  instrumentId: string,
  form: PaperTicketForm,
  mode: PaperTicketMode,
  symbolOf: (instrumentId: string) => string = (id) => id,
): { kind: 'success' | 'error'; message: string } {
  if (prefill.instrumentId !== instrumentId) {
    return { kind: 'error', message: `The drawing is on ${symbolOf(prefill.instrumentId)}; open that chart to trade it.` };
  }
  form.setTicketTab('order');
  form.setSide(prefill.side);
  form.setOrderType('limit');
  form.setTriggerPrice(String(prefill.entry));
  form.setLimitPrice('');
  const protect = mode.riskManaged;
  form.setStopLossEnabled(protect && prefill.stop !== null);
  form.setStopLoss(protect && prefill.stop !== null ? String(prefill.stop) : '');
  form.setTakeProfitEnabled(protect && prefill.target !== null);
  form.setTakeProfit(protect && prefill.target !== null ? String(prefill.target) : '');
  if (!protect && prefill.quantity !== null) form.setQuantity(String(Number(prefill.quantity.toPrecision(6))));
  const detail = protect
    ? `The account's ${mode.riskPercent}% risk rule sizes the quantity.`
    : 'This order can\'t carry a stop and target: add them after it fills.';
  return { kind: 'success', message: `Ticket filled from the position drawing. ${detail} Check it, then place the order.` };
}

/** Panel side: calls `apply` with each pre-fill, also one left before the panel mounted. */
export function usePaperTicketPrefill(apply: (prefill: PaperTicketPrefill) => void): void {
  const handler = useRef(apply);
  useEffect(() => {
    handler.current = apply;
  });
  useEffect(() => {
    const take = () => {
      const prefill = takePaperTicketPrefill();
      if (prefill) handler.current(prefill);
    };
    take();
    return onPaperTicketRequest(take);
  }, []);
}
