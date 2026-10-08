import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { clearPaperNotifications, orderNotifications, usePaperNotifications, usePaperOrderNotifications } from './paperNotifications';
import type { PaperAccountSnapshot, PaperOrder } from './paperTypes';
import { TradingNotificationsLog } from './TradingNotificationsLog';
import { TradingOrderToastLayer } from './TradingOrderToastLayer';

const order = (id: string, status: PaperOrder['status'], extra: Partial<PaperOrder> = {}) => ({
  order_id: id, instrument_id: 'crypto:BINANCE:spot:BTC-USDT', side: 'buy', order_type: 'market', quantity: '2', status, updated_at: '2026-10-08T14:00:00Z', ...extra,
}) as PaperOrder;

const snapshot = (accountId: string, orders: PaperOrder[]) => ({
  account: { account_id: accountId }, balances: [], positions: [], open_orders: orders.filter((item) => item.status === 'open'), order_history: orders,
}) as unknown as PaperAccountSnapshot;

afterEach(() => act(() => clearPaperNotifications()));

describe('paper order notifications (TVP-7.4)', () => {
  it('reports fills, rejections, cancellations and expiries between snapshots', () => {
    const before = snapshot('a', [order('1', 'open'), order('2', 'open'), order('3', 'filled')]);
    const after = snapshot('a', [
      order('1', 'filled', { average_fill_price: '101.5' }),
      order('2', 'rejected', { rejection_reason: 'insufficient_paper_cash' }),
      order('3', 'filled'),
      order('4', 'expired', { side: 'sell', order_type: 'limit' }),
      order('5', 'open'),
    ]);
    expect(orderNotifications(before, after).map((item) => [item.kind, item.message])).toEqual([
      ['fill', 'Buy 2 BTC/USDT MARKET filled at 101.5'],
      ['reject', 'Buy 2 BTC/USDT MARKET rejected: insufficient paper cash'],
      ['expire', 'Sell 2 BTC/USDT LIMIT expired'],
    ]);
  });

  it('starts from the first snapshot of an account, logs, toasts and clears', () => {
    const { rerender } = renderHook(({ value }) => usePaperOrderNotifications(value), { initialProps: { value: snapshot('a', [order('1', 'filled')]) } });
    const log = renderHook(() => usePaperNotifications());
    expect(log.result.current).toEqual([]);
    rerender({ value: snapshot('b', [order('9', 'filled')]) });
    expect(log.result.current).toEqual([]);
    rerender({ value: snapshot('b', [order('9', 'filled'), order('10', 'cancelled')]) });
    expect(log.result.current.map((item) => item.kind)).toEqual(['cancel']);
    render(<><TradingOrderToastLayer /><TradingNotificationsLog /></>);
    expect(screen.getByRole('status')).toHaveTextContent('Order cancelled');
    expect(screen.getByRole('table')).toHaveTextContent('Buy 2 BTC/USDT MARKET cancelled');
    fireEvent.click(screen.getByRole('button', { name: 'Clear notifications' }));
    expect(screen.getByText('No notifications yet')).toBeInTheDocument();
  });
});
