import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { tradingApi } from './tradingApi';
import type { BarsResponse, CanonicalInstrument, TradingDocument } from './tradingTypes';
import { TradingWatchlist } from './TradingWatchlist';

const apple: CanonicalInstrument = {
  instrument_id: 'equity:NASDAQ:AAPL',
  asset_class: 'equity',
  instrument_type: 'equity',
  venue: 'NASDAQ',
  venue_symbol: 'AAPL',
  display_symbol: 'AAPL',
  base_currency: null,
  quote_currency: 'USD',
  exchange_timezone: 'America/New_York',
  session_calendar: 'XNAS',
  price_scale: 100,
  minimum_tick: '0.01',
  status: 'active',
};

const record = {
  record_id: 'default',
  revision: 1,
  payload: {
    name: 'Default Watchlist',
    instrumentIds: [apple.instrument_id],
  },
} as TradingDocument;

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TradingWatchlist add symbol', () => {
  it('keeps the toolbar plus enabled when the active symbol is already listed and opens the symbol picker', async () => {
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([record]);
    vi.spyOn(tradingApi, 'quote').mockResolvedValue({ price: '100' });
    vi.spyOn(tradingApi, 'bars').mockResolvedValue({
      bars: [],
      binding: { supported_intervals: ['1m'] },
    } as unknown as BarsResponse);

    render(
      <TradingWatchlist
        instruments={[apple]}
        activeInstrumentId={apple.instrument_id}
        interval="1m"
        onSelect={vi.fn()}
      />,
    );

    const addSymbol = await screen.findByRole('button', { name: 'Add symbol to watchlist' });
    await waitFor(() => expect(addSymbol).toBeEnabled());

    fireEvent.click(addSymbol);

    expect(screen.getByRole('dialog', { name: 'Add symbol' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'AAPL already in watchlist' })).toBeDisabled();
  });
});
