import { describe, expect, it, vi } from 'vitest';
import { dispatchDrawingActionRequest } from './drawings/drawingActions';
import { applyPaperTicketPrefill, takePaperTicketPrefill, type PaperTicketForm } from './paperTicketRequests';
import { renderHook } from '@testing-library/react';
import { usePaperTicketRequests } from './paperTicketRequests';

function form(): PaperTicketForm & Record<string, ReturnType<typeof vi.fn>> {
  const names = ['setTicketTab', 'setSide', 'setOrderType', 'setLimitPrice', 'setStopLossEnabled', 'setStopLoss', 'setTakeProfitEnabled', 'setTakeProfit', 'setQuantity'];
  return Object.fromEntries(names.map((name) => [name, vi.fn()])) as unknown as PaperTicketForm & Record<string, ReturnType<typeof vi.fn>>;
}

describe('order ticket from a position drawing (TVP-3.6)', () => {
  it('fills a limit order with the stop and target, for the drawing\'s symbol only', () => {
    const fields = form();
    const prefill = { instrumentId: 'crypto:BTC', side: 'sell' as const, entry: 100, stop: 105, target: 90, quantity: 1.234567891 };
    expect(applyPaperTicketPrefill(prefill, 'crypto:BTC', fields)).toMatchObject({ kind: 'success' });
    expect(fields.setSide).toHaveBeenCalledWith('sell');
    expect(fields.setOrderType).toHaveBeenCalledWith('limit');
    expect(fields.setLimitPrice).toHaveBeenCalledWith('100');
    expect(fields.setStopLoss).toHaveBeenCalledWith('105');
    expect(fields.setTakeProfit).toHaveBeenCalledWith('90');
    expect(fields.setQuantity).toHaveBeenCalledWith('1.23457');
    const other = form();
    expect(applyPaperTicketPrefill(prefill, 'crypto:ETH', other, () => 'BTC')).toEqual({ kind: 'error', message: 'The drawing is on BTC; open that chart to trade it.' });
    expect(other.setSide).not.toHaveBeenCalled();
  });

  it('the workspace opens the paper panel and leaves the pre-fill for it', () => {
    const open = vi.fn();
    const hook = renderHook(() => usePaperTicketRequests(open));
    dispatchDrawingActionRequest({ type: 'order-ticket', payload: { instrumentId: 'crypto:BTC', side: 'buy', entry: 100, stop: 95, target: 110, quantity: 4 } });
    expect(open).toHaveBeenCalledTimes(1);
    expect(takePaperTicketPrefill()).toMatchObject({ entry: 100, quantity: 4 });
    expect(takePaperTicketPrefill()).toBeNull();
    // Malformed requests are ignored.
    dispatchDrawingActionRequest({ type: 'order-ticket', payload: { side: 'buy' } });
    expect(open).toHaveBeenCalledTimes(1);
    hook.unmount();
  });
});
