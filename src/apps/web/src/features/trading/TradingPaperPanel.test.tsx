import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const paperApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  snapshot: vi.fn(),
  createAccount: vi.fn(),
  placeOrder: vi.fn(),
  processObservation: vi.fn(),
  resetAccount: vi.fn(),
  archiveAccount: vi.fn(),
}));

const tradingApi = vi.hoisted(() => ({
  quote: vi.fn(),
}));

vi.mock('./tradingPaperApi', () => ({ tradingPaperApi: paperApi }));
vi.mock('./tradingApi', () => ({ tradingApi }));

import { TradingPaperPanel } from './TradingPaperPanel';
import { useTradingReplayStore } from './tradingReplayStore';
import { useTradingStore } from './tradingStore';

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
    useTradingStore.setState({ replayMode: false, replaySessionId: 0 });
    useTradingReplayStore.getState().clear();
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
    paperApi.processObservation.mockResolvedValue({ fills: [] });
    paperApi.placeOrder.mockRejectedValue(new Error('Paper Trading request failed (422): insufficient_paper_cash'));
  });

  afterEach(() => {
    useTradingStore.setState({ replayMode: false });
    useTradingReplayStore.getState().clear();
    vi.clearAllMocks();
  });

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

  it('immediately observes an accepted market order that is still open', async () => {
    paperApi.placeOrder.mockResolvedValue({ status: 'open', reference_price: '75.62' });

    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);

    const quantity = await screen.findByRole('textbox', { name: 'Order quantity' });
    fireEvent.change(quantity, { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ }));

    await screen.findByRole('status');
    expect(paperApi.processObservation).toHaveBeenCalledWith('paper-1', expect.objectContaining({
      instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
      provider: 'paper-reference',
      price: '75.62',
    }));
  });

  it('uses the replay bar price without creating a persisted paper order', async () => {
    useTradingStore.setState({ replayMode: true, replaySessionId: 7 });
    useTradingReplayStore.getState().setBar({
      instrument_id: 'crypto:BINANCE:spot:SOL-USDT', interval: '1h',
      start_time: '2024-01-02T10:00:00Z', end_time: '2024-01-02T11:00:00Z',
      open: '100', high: '103', low: '99', close: '101.25', volume: '10', is_final: true,
      adjustment_mode: 'raw', session: '24x7', provider: 'replay-test',
      provider_event_id: null, provider_sequence: null, ingestion_revision: 1,
      received_at: '2024-01-02T11:00:01Z',
    });

    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);

    await screen.findByRole('textbox', { name: 'Order quantity' });
    expect(await screen.findByText('Replay only')).toBeInTheDocument();
    expect(screen.getAllByText('101.25').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Buy 1 SOL\/USDT MARKET/ }));

    expect(await screen.findByRole('status')).toHaveTextContent('Market order executed on');
    expect(paperApi.placeOrder).not.toHaveBeenCalled();
    expect(paperApi.processObservation).not.toHaveBeenCalled();
    expect(useTradingReplayStore.getState().snapshot?.order_history).toHaveLength(1);
    expect(useTradingReplayStore.getState().snapshot?.order_history?.[0]).toMatchObject({
      status: 'filled', average_fill_price: '101.25',
    });
  });
});
