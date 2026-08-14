import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const paperApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  snapshot: vi.fn(),
  createAccount: vi.fn(),
  placeOrder: vi.fn(),
  cancelOrder: vi.fn(),
}));

vi.mock('./tradingPaperApi', () => ({ tradingPaperApi: paperApi }));

import { TradingTerminalDock } from './TradingTerminalDock';

describe('TradingTerminalDock', () => {
  beforeEach(() => {
    paperApi.accounts.mockResolvedValue([]);
    paperApi.snapshot.mockResolvedValue(null);
  });

  afterEach(() => vi.clearAllMocks());

  it('minimizes the dock while keeping the restore control visible', async () => {
    render(<TradingTerminalDock instrumentId="crypto:BINANCE:spot:BTC-USDT" bindingId={null} />);
    await waitFor(() => expect(screen.getByText('No paper account')).toBeInTheDocument());

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
});
