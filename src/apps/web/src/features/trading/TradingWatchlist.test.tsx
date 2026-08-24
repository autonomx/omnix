import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { tradingApi } from './tradingApi';
import type { BarsResponse, CanonicalInstrument, ProviderBinding, TradingDocument } from './tradingTypes';
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
} as unknown as TradingDocument;

const gameStop: CanonicalInstrument = {
  ...apple,
  instrument_id: 'equity:NYSE:GME',
  venue: 'NYSE',
  venue_symbol: 'GME',
  display_symbol: 'GME',
};

const otcEquity: CanonicalInstrument = {
  ...apple,
  instrument_id: 'equity:PNK:GMETF',
  venue: 'PNK',
  venue_symbol: 'GMETF',
  display_symbol: 'GMETF',
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TradingWatchlist add symbol', () => {
  it('does not restore deleted default symbols after reload', async () => {
    const persisted = {
      ...record,
      payload: {
        name: 'Default Watchlist',
        instrumentIds: [apple.instrument_id],
      },
    } as TradingDocument;
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([persisted]);
    const update = vi.spyOn(tradingApi, 'updateDocument');
    vi.spyOn(tradingApi, 'quote').mockResolvedValue({ price: '100' });
    vi.spyOn(tradingApi, 'bars').mockResolvedValue({
      bars: [],
      binding: { supported_intervals: ['1m'] },
    } as unknown as BarsResponse);

    render(
      <TradingWatchlist
        instruments={[apple, gameStop]}
        activeInstrumentId={apple.instrument_id}
        interval="1m"
        onSelect={vi.fn()}
      />,
    );

    await screen.findByRole('button', { name: 'Select AAPL' });
    expect(screen.queryByRole('button', { name: 'Select GME' })).not.toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
  });

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

  it('does not request unsupported intraday bars for OTC symbols', async () => {
    const otcRecord = {
      ...record,
      payload: {
        name: 'Default Watchlist',
        instrumentIds: [otcEquity.instrument_id],
      },
    } as TradingDocument;
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([otcRecord]);
    const quote = vi.spyOn(tradingApi, 'quote').mockResolvedValue({ price: '0.008' });
    const bars = vi.spyOn(tradingApi, 'bars');

    render(
      <TradingWatchlist
        instruments={[otcEquity]}
        providerBindings={[{
          instrument_id: otcEquity.instrument_id,
          supported_intervals: ['1d', '1w', '1mo'],
        } as unknown as ProviderBinding]}
        activeInstrumentId={otcEquity.instrument_id}
        interval="2h"
        onSelect={vi.fn()}
      />,
    );

    await screen.findByRole('button', { name: 'Select GMETF' });
    await waitFor(() => expect(quote).toHaveBeenCalledWith(otcEquity.instrument_id));
    expect(bars).not.toHaveBeenCalled();
  });

  it('keeps the last known values visible when returning to the watchlist', async () => {
    const instruments = [apple];
    let resolveRefresh: (value: { price: string }) => void = () => undefined;
    const refreshQuote = new Promise<{ price: string }>((resolve) => {
      resolveRefresh = resolve;
    });
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([record]);
    vi.spyOn(tradingApi, 'quote')
      .mockResolvedValueOnce({ price: '100' })
      .mockImplementationOnce(() => refreshQuote);
    vi.spyOn(tradingApi, 'bars').mockResolvedValue({
      bars: [{ open: '100', close: '100', start_time: '2026-01-01T00:00:00Z' }],
      binding: { supported_intervals: ['1m', '5m'] },
    } as unknown as BarsResponse);

    const view = render(
      <TradingWatchlist
        instruments={instruments}
        activeInstrumentId={apple.instrument_id}
        interval="1m"
        onSelect={vi.fn()}
      />,
    );

    expect(await screen.findByText('100.00')).toBeInTheDocument();

    view.unmount();
    render(
      <TradingWatchlist
        instruments={instruments}
        activeInstrumentId={apple.instrument_id}
        interval="5m"
        onSelect={vi.fn()}
      />,
    );

    expect(await screen.findByText('100.00')).toBeInTheDocument();
    resolveRefresh({ price: '105' });
    await waitFor(() => expect(screen.getByText('105.00')).toBeInTheDocument());
  });

  it('reorders symbols immediately with the row arrows and persists the new order', async () => {
    const orderedRecord = {
      ...record,
      payload: {
        name: 'Default Watchlist',
        instrumentIds: [apple.instrument_id, gameStop.instrument_id],
      },
    } as TradingDocument;
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([orderedRecord]);
    vi.spyOn(tradingApi, 'quote').mockResolvedValue({ price: '100' });
    vi.spyOn(tradingApi, 'bars').mockResolvedValue({
      bars: [],
      binding: { supported_intervals: ['1m'] },
    } as unknown as BarsResponse);
    const update = vi.spyOn(tradingApi, 'updateDocument').mockImplementation(async (_kind, currentRecord, nextPayload) => ({
      ...currentRecord,
      revision: currentRecord.revision + 1,
      payload: nextPayload,
    }));

    render(
      <TradingWatchlist
        instruments={[apple, gameStop]}
        activeInstrumentId={apple.instrument_id}
        interval="1m"
        onSelect={vi.fn()}
      />,
    );

    await screen.findByRole('button', { name: 'Move GME up' });
    const selectedSymbols = () => screen.getAllByRole('button', { name: /^Select / }).map((button) => button.querySelector('strong')?.textContent);

    fireEvent.click(screen.getByRole('button', { name: 'Move GME up' }));
    await waitFor(() => expect(selectedSymbols()).toEqual(['GME', 'AAPL']));
    expect(update).toHaveBeenCalledWith(
      'watchlists',
      orderedRecord,
      expect.objectContaining({ instrumentIds: [gameStop.instrument_id, apple.instrument_id] }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Move GME down' }));
    await waitFor(() => expect(selectedSymbols()).toEqual(['AAPL', 'GME']));
  });

  it('sorts symbols by percentage change without changing the saved order', async () => {
    const sortableRecord = {
      ...record,
      payload: {
        name: 'Default Watchlist',
        instrumentIds: [gameStop.instrument_id, apple.instrument_id],
      },
    } as TradingDocument;
    vi.spyOn(tradingApi, 'documents').mockResolvedValue([sortableRecord]);
    vi.spyOn(tradingApi, 'quote').mockImplementation(async (instrumentId) => ({
      price: instrumentId === gameStop.instrument_id ? '90' : '110',
    }));
    vi.spyOn(tradingApi, 'bars').mockResolvedValue({
      bars: [{ open: '100', close: '100', start_time: '2026-01-01T00:00:00Z' }],
      binding: { supported_intervals: ['1m'] },
    } as unknown as BarsResponse);

    render(
      <TradingWatchlist
        instruments={[apple, gameStop]}
        activeInstrumentId={apple.instrument_id}
        interval="1m"
        onSelect={vi.fn()}
      />,
    );

    await screen.findByRole('button', { name: 'Select GME' });
    const selectedSymbols = () => screen.getAllByRole('button', { name: /^Select / }).map((button) => button.querySelector('strong')?.textContent);
    const sortByChange = () => screen.getByRole('button', { name: /watchlist.*change percentage/ });

    await waitFor(() => expect(selectedSymbols()).toEqual(['GME', 'AAPL']));
    fireEvent.click(sortByChange());
    await waitFor(() => expect(selectedSymbols()).toEqual(['AAPL', 'GME']));
    fireEvent.click(sortByChange());
    await waitFor(() => expect(selectedSymbols()).toEqual(['GME', 'AAPL']));
    fireEvent.click(sortByChange());
    await waitFor(() => expect(selectedSymbols()).toEqual(['GME', 'AAPL']));
  });

  it('retries symbol removal after a stale watchlist revision conflict', async () => {
    const twoSymbolRecord = {
      ...record,
      payload: {
        name: 'Default Watchlist',
        instrumentIds: [apple.instrument_id, gameStop.instrument_id],
      },
    } as TradingDocument;
    const updatedRecord = {
      ...twoSymbolRecord,
      revision: 3,
      payload: {
        name: 'Default Watchlist',
        instrumentIds: [gameStop.instrument_id],
      },
    } as TradingDocument;
    const documents = vi.spyOn(tradingApi, 'documents')
      .mockResolvedValueOnce([twoSymbolRecord])
      .mockResolvedValueOnce([twoSymbolRecord])
      .mockResolvedValueOnce([twoSymbolRecord]);
    vi.spyOn(tradingApi, 'quote').mockResolvedValue({ price: '100' });
    vi.spyOn(tradingApi, 'bars').mockResolvedValue({
      bars: [],
      binding: { supported_intervals: ['1m'] },
    } as unknown as BarsResponse);
    const update = vi.spyOn(tradingApi, 'updateDocument')
      .mockRejectedValueOnce(new Error('Trading request failed (409): revision conflict'))
      .mockRejectedValueOnce(new Error('Trading request failed (409): revision conflict'))
      .mockResolvedValueOnce(updatedRecord);

    render(
      <TradingWatchlist
        instruments={[apple, gameStop]}
        activeInstrumentId={apple.instrument_id}
        interval="1m"
        onSelect={vi.fn()}
      />,
    );

    await screen.findByRole('button', { name: 'Remove AAPL' });
    fireEvent.click(screen.getByRole('button', { name: 'Remove AAPL' }));

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Select AAPL' })).not.toBeInTheDocument());
    expect(update).toHaveBeenCalledTimes(3);
    expect(documents).toHaveBeenCalledTimes(3);
  });
});
