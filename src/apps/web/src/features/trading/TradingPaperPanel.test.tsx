import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const paperApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  snapshot: vi.fn(),
  createAccount: vi.fn(),
  riskPreview: vi.fn(),
  placeRiskOrder: vi.fn(),
  placeOrder: vi.fn(),
  processObservation: vi.fn(),
  resetAccount: vi.fn(),
  archiveAccount: vi.fn(),
}));

const replayApi = vi.hoisted(() => ({
  advanceExecution: vi.fn(),
  placeExecutionOrder: vi.fn(),
}));

const tradingApi = vi.hoisted(() => ({
  quote: vi.fn(),
}));

vi.mock('./tradingPaperApi', () => ({ tradingPaperApi: paperApi }));
vi.mock('./tradingReplayApi', () => ({ tradingReplayApi: replayApi }));
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

const accountSnapshot = () => ({
  account,
  balances: [{ currency: 'USD', available: '0', reserved: '100000' }],
  positions: [],
  open_orders: [],
  order_history: [],
  recent_fills: [],
  recent_ledger: [],
});

const riskPreview = () => ({
  allowed: true,
  policy_version: 'paper-risk-v1',
  reason_codes: [],
  limiting_reason_code: 'RISK_BUDGET',
  recommended_quantity: '3',
  account_equity: '100000',
  desired_risk_pct: '0.35',
  actual_risk_dollars: '350',
  actual_risk_pct: '0.35',
  estimated_notional: '226.86',
  buying_power_before: '100000',
  buying_power_after: '99773.14',
  aggregate_open_risk_dollars: '0',
  aggregate_open_risk_pct: '0',
  daily_realized_pnl: '0',
  daily_loss_remaining: '1500',
  spread_bps: '2.64',
  observation_age_seconds: '0.1',
  freshness_mode: 'polled',
  execution_eligible: true,
  unprotected_exposure_count: 0,
});

async function prepareRiskManagedBuy() {
  fireEvent.click(await screen.findByRole('switch', { name: 'Enable stop loss' }));
  fireEvent.change(await screen.findByRole('textbox', { name: 'Stop loss price' }), { target: { value: '74.50' } });
  await waitFor(() => expect(paperApi.riskPreview).toHaveBeenCalledWith('paper-1', expect.objectContaining({
    instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
    entry_price: '75.62',
    stop_price: '74.5',
    desired_risk_pct: '0.35',
  })));
  await screen.findByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ });
}

describe('TradingPaperPanel', () => {
  beforeEach(() => {
    useTradingStore.setState({ replayMode: false, replaySessionId: 0 });
    useTradingReplayStore.getState().clear();
    paperApi.accounts.mockResolvedValue([account]);
    paperApi.snapshot.mockResolvedValue(accountSnapshot());
    tradingApi.quote.mockResolvedValue({ price: '75.61', bid: '75.60', ask: '75.62' });
    paperApi.riskPreview.mockResolvedValue(riskPreview());
    paperApi.processObservation.mockResolvedValue({ fills: [] });
    paperApi.placeRiskOrder.mockRejectedValue(new Error('Paper Trading request failed (422): insufficient_paper_cash'));
    paperApi.placeOrder.mockRejectedValue(new Error('Paper Trading request failed (422): insufficient_paper_cash'));
    replayApi.advanceExecution.mockImplementation(async (snapshot) => snapshot);
    replayApi.placeExecutionOrder.mockImplementation(async (snapshot, order) => {
      const filled = {
        account_id: snapshot.account.account_id,
        ...order,
        status: 'filled',
        filled_quantity: order.quantity,
        average_fill_price: '101.35125',
        reserved_cash: '0',
      };
      return {
        snapshot: {
          ...snapshot,
          order_history: [...(snapshot.order_history ?? []), filled],
          open_orders: [],
        },
        order: filled,
      };
    });
  });

  afterEach(() => {
    useTradingStore.setState({ replayMode: false });
    useTradingReplayStore.getState().clear();
    vi.clearAllMocks();
  });

  it('shows the server rejection when a risk-sized order cannot be funded', async () => {
    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);
    await prepareRiskManagedBuy();

    const quantity = screen.getByRole('textbox', { name: 'Order quantity' });
    expect(quantity).toHaveValue('3');
    expect(quantity).toHaveAttribute('readonly');
    fireEvent.click(screen.getByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Order not placed: insufficient available paper cash. Check reserved funds or wait for an open order to fill.',
    );
    expect(paperApi.placeRiskOrder).toHaveBeenCalledWith('paper-1', expect.objectContaining({
      stop_loss: '74.50',
      desired_risk_pct: '0.35',
    }));
    expect(paperApi.placeRiskOrder.mock.calls[0][1]).not.toHaveProperty('quantity');
    expect(paperApi.placeOrder).not.toHaveBeenCalled();
  });

  it('shows a confirmation after the server accepts a risk-sized paper entry', async () => {
    paperApi.placeRiskOrder.mockResolvedValue({
      preview: riskPreview(),
      order: {
        status: 'filled',
        order_id: 'risk-order',
        quantity: '3',
        average_fill_price: '75.63',
        limit_price: null,
        stop_price: null,
        reference_price: '75.62',
      },
      protection: { entry_order_id: 'risk-order', stop_loss: '74.50' },
    });

    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);
    await prepareRiskManagedBuy();
    fireEvent.click(screen.getByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ }));

    const confirmation = await screen.findByRole('status');
    expect(confirmation).toHaveClass('trading-paper-confirmation-toast');
    expect(confirmation).toHaveTextContent('Market order executed on');
    expect(confirmation).toHaveTextContent('BINANCE:SOLUSDT');
    expect(confirmation).toHaveTextContent('Buy 3');
    expect(paperApi.placeRiskOrder.mock.calls[0][1]).not.toHaveProperty('quantity');
  });

  it('leaves an accepted risk-sized market order to server-authoritative execution', async () => {
    paperApi.placeRiskOrder.mockResolvedValue({
      preview: riskPreview(),
      order: {
        status: 'open',
        order_id: 'risk-order',
        quantity: '3',
        reference_price: '75.62',
        average_fill_price: null,
        limit_price: null,
        stop_price: null,
      },
      protection: { entry_order_id: 'risk-order', stop_loss: '74.50' },
    });

    render(<TradingPaperPanel instrumentId="crypto:BINANCE:spot:SOL-USDT" bindingId={null} />);
    await prepareRiskManagedBuy();
    fireEvent.click(screen.getByRole('button', { name: /Buy 3 SOL\/USDT MARKET/ }));

    expect(await screen.findByRole('status')).toHaveTextContent('Market order submitted on');
    expect(paperApi.placeRiskOrder).toHaveBeenCalledWith('paper-1', expect.objectContaining({
      instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
      order_type: 'market',
      trigger_price: null,
      stop_loss: '74.50',
    }));
    expect(paperApi.placeRiskOrder.mock.calls[0][1]).not.toHaveProperty('quantity');
    expect(paperApi.processObservation).not.toHaveBeenCalled();
  });

  it('uses the replay bar through the shared server kernel without creating a persisted paper order', async () => {
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
    expect(paperApi.placeRiskOrder).not.toHaveBeenCalled();
    expect(paperApi.processObservation).not.toHaveBeenCalled();
    expect(replayApi.placeExecutionOrder).toHaveBeenCalledWith(
      expect.objectContaining({ account: expect.objectContaining({ account_id: 'paper-1' }) }),
      expect.objectContaining({ quantity: '1', reference_price: '101.25' }),
      expect.objectContaining({ close: '101.25' }),
    );
    await waitFor(() => expect(useTradingReplayStore.getState().snapshot?.order_history).toHaveLength(1));
    expect(useTradingReplayStore.getState().snapshot?.order_history?.[0]).toMatchObject({
      status: 'filled', average_fill_price: '101.35125',
    });
  });
});