import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const paperApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  snapshot: vi.fn(),
  createAccount: vi.fn(),
  placeOrder: vi.fn(),
  resetAccount: vi.fn(),
  archiveAccount: vi.fn(),
}));

const tradingApi = vi.hoisted(() => ({
  quote: vi.fn(),
}));

vi.mock('./tradingPaperApi', () => ({ tradingPaperApi: paperApi }));
vi.mock('./tradingApi', () => ({ tradingApi }));

import { TradingPaperPanel } from './TradingPaperPanel';

const account = {
  account_id: 'paper-1',
  name: 'Paper Account 1',
  base_currency: 'USD',
  commission_bps: '0',
  enabled: true,
  revision: 1,
};

describe('TradingPaperPanel', () => {
  beforeEach(() => {
    paperApi.accounts.mockResolvedValue([account]);
    paperApi.snapshot.mockResolvedValue({
      account,
      balances: [{ currency: 'USD', available: '0', reserved: '100000' }],
      positions: [],
      open_orders: [],
      recent_fills: [],
      recent_ledger: [],
    });
    tradingApi.quote.mockResolvedValue({ price: '75.61', bid: '75.60', ask: '75.62' });
    paperApi.placeOrder.mockRejectedValue(new Error('Paper Trading request failed (422): insufficient_paper_cash'));
  });

  afterEach(() => vi.clearAllMocks());

  it('shows the server rejection when an order cannot be funded', async () => {
    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);

    const quantity = await screen.findByRole('textbox', { name: 'Order quantity' });
    fireEvent.change(quantity, { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Order not placed: insufficient available paper cash. Check reserved funds or wait for an open order to fill.',
    );
    expect(paperApi.placeOrder).toHaveBeenCalledWith('paper-1', expect.objectContaining({ quantity: '3' }));
  });

  it('shows a confirmation tooltip after a paper order is accepted', async () => {
    paperApi.placeOrder.mockResolvedValue({ status: 'filled' });

    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);

    const quantity = await screen.findByRole('textbox', { name: 'Order quantity' });
    fireEvent.change(quantity, { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ }));

    const confirmation = await screen.findByRole('status');
    expect(confirmation).toHaveClass('trading-paper-confirmation-toast');
    expect(confirmation).toHaveTextContent('Market order executed on');
    expect(confirmation).toHaveTextContent('BINANCE:SOLUSDT');
    expect(confirmation).toHaveTextContent('Buy 3');
  });
});
