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

let pending: PaperTicketPrefill | null = null;
const listeners = new Set<() => void>();

export function requestPaperTicket(prefill: PaperTicketPrefill): void {
  pending = prefill;
  for (const listener of listeners) listener();
}

/** Takes the pending pre-fill (once). */
export function takePaperTicketPrefill(): PaperTicketPrefill | null {
  const taken = pending;
  pending = null;
  return taken;
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
  setLimitPrice: (value: string) => void;
  setStopLossEnabled: (enabled: boolean) => void;
  setStopLoss: (value: string) => void;
  setTakeProfitEnabled: (enabled: boolean) => void;
  setTakeProfit: (value: string) => void;
  setQuantity: (value: string) => void;
};

/**
 * Fills the ticket from a pre-fill: a limit order at the entry with its stop and target as protection, and the
 * drawing's quantity. Returns the notice to show; a drawing on another symbol fills nothing.
 */
export function applyPaperTicketPrefill(
  prefill: PaperTicketPrefill,
  instrumentId: string,
  form: PaperTicketForm,
  symbolOf: (instrumentId: string) => string = (id) => id,
): { kind: 'success' | 'error'; message: string } {
  if (prefill.instrumentId !== instrumentId) {
    return { kind: 'error', message: `The drawing is on ${symbolOf(prefill.instrumentId)}; open that chart to trade it.` };
  }
  form.setTicketTab('order');
  form.setSide(prefill.side);
  form.setOrderType('limit');
  form.setLimitPrice(String(prefill.entry));
  form.setStopLossEnabled(prefill.stop !== null);
  form.setStopLoss(prefill.stop === null ? '' : String(prefill.stop));
  form.setTakeProfitEnabled(prefill.target !== null);
  form.setTakeProfit(prefill.target === null ? '' : String(prefill.target));
  if (prefill.quantity !== null) form.setQuantity(String(Number(prefill.quantity.toPrecision(6))));
  return { kind: 'success', message: 'Ticket filled from the position drawing. Check it, then place the order.' };
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
