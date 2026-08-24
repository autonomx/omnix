import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const paperApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  snapshot: vi.fn(),
  createAccount: vi.fn(),
  placeOrder: vi.fn(),
}));

vi.mock('./tradingPaperApi', () => ({ tradingPaperApi: paperApi }));
vi.mock('./TradingPaperDashboard', () => ({ TradingPaperDashboard: () => <div>Paper trading dashboard view</div> }));

import { TradingTerminalDock } from './TradingTerminalDock';

describe('TradingTerminalDock', () => {
  beforeEach(() => {
    paperApi.accounts.mockResolvedValue([]);
    paperApi.snapshot.mockResolvedValue(null);
  });

  afterEach(() => vi.clearAllMocks());

  it('minimizes the dock while keeping the restore control visible', async () => {
    render(<TradingTerminalDock instrumentId="crypto:BINANCE:spot:BTC-USDT" bindingId={null} />);
    expect(screen.queryByText('No paper account')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Restore paper trading panel' })).toHaveAttribute('aria-expanded', 'false');

    await act(async () => {
      screen.getByRole('button', { name: 'Restore paper trading panel' }).click();
    });
    await waitFor(() => expect(screen.getByText('No paper account')).toBeInTheDocument());
    expect(screen.queryByRole('complementary', { name: 'Paper order ticket' })).not.toBeInTheDocument();

    await act(async () => {
      screen.getByRole('button', { name: 'Minimize paper trading panel' }).click();
    });

    expect(screen.queryByText('No paper account')).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Paper order ticket' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Restore paper trading panel' })).toHaveAttribute('aria-expanded', 'false');

    await act(async () => {
      screen.getByRole('button', { name: 'Restore paper trading panel' }).click();
    });
    expect(screen.getByText('No paper account')).toBeInTheDocument();
  });

  it('opens the dedicated dashboard from the paper trading dock', async () => {
    render(<TradingTerminalDock instrumentId="crypto:BINANCE:spot:BTC-USDT" bindingId={null} />);

    await act(async () => {
      screen.getByRole('button', { name: 'Restore paper trading panel' }).click();
    });
    await act(async () => {
      screen.getByRole('tab', { name: 'Dashboard' }).click();
    });

    expect(screen.getByText('Paper trading dashboard view')).toBeInTheDocument();
    expect(screen.queryByText('No paper account')).not.toBeInTheDocument();
  });

  it('projects a working order into the open positions view', async () => {
    const account = {
      account_id: 'paper-1', name: 'Paper account', base_currency: 'USD', commission_bps: '0',
      enabled: true, revision: 1,
    };
    const workingOrder = {
      account_id: account.account_id, order_id: 'order-1', instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
      binding_id: null, side: 'buy', order_type: 'market', quantity: '3', limit_price: null,
      stop_price: null, reference_price: '75.17', status: 'open', filled_quantity: '0',
      average_fill_price: null, idempotency_key: 'key-1', rejection_reason: null, reserved_cash: '0',
    };
    paperApi.accounts.mockResolvedValue([account]);
    paperApi.snapshot.mockResolvedValue({
      account,
      balances: [{ currency: 'USD', available: '100000', reserved: '0' }],
      positions: [],
      open_orders: [workingOrder],
      order_history: [workingOrder],
      recent_fills: [],
      recent_ledger: [],
    });

    render(<TradingTerminalDock instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);
    await waitFor(() => expect(paperApi.snapshot).toHaveBeenCalledWith(account.account_id));

    await act(async () => {
      screen.getByRole('button', { name: 'Restore paper trading panel' }).click();
    });

    expect(screen.getByRole('tab', { name: 'Positions 1' })).toBeInTheDocument();
    expect(screen.getByText('BINANCE:SOLUSDT')).toBeInTheDocument();
    expect(screen.getByText('Working')).toBeInTheDocument();
  });

  it('shows the rejection reason in an order status tooltip', async () => {
    const account = {
      account_id: 'paper-1', name: 'Paper account', base_currency: 'USD', commission_bps: '0',
      enabled: true, revision: 1,
    };
    const rejectedOrder = {
      account_id: account.account_id, order_id: 'order-rejected', instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
      binding_id: null, side: 'buy', order_type: 'market', quantity: '5', limit_price: null,
      stop_price: null, reference_price: '74.55', status: 'rejected', filled_quantity: '0',
      average_fill_price: null, idempotency_key: 'key-rejected', rejection_reason: 'insufficient_paper_cash',
      reserved_cash: '0',
    };
    paperApi.accounts.mockResolvedValue([account]);
    paperApi.snapshot.mockResolvedValue({
      account,
      balances: [{ currency: 'USD', available: '100000', reserved: '0' }],
      positions: [],
      open_orders: [],
      order_history: [rejectedOrder],
      recent_fills: [],
      recent_ledger: [],
    });

    render(<TradingTerminalDock instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);
    await waitFor(() => expect(paperApi.snapshot).toHaveBeenCalledWith(account.account_id));
    await act(async () => {
      screen.getByRole('button', { name: 'Restore paper trading panel' }).click();
    });
    await act(async () => {
      screen.getByRole('tab', { name: 'Orders' }).click();
    });

    expect(screen.getByRole('tooltip')).toHaveTextContent('Insufficient available paper cash at the fill price.');
    expect(screen.getByTitle('Insufficient available paper cash at the fill price.')).toBeInTheDocument();
  });
});