import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { fixture } from '../../test/fixture';
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

function mockDocuments(watchlists: TradingDocument[], flagSets: TradingDocument[] = []) {
  return vi.spyOn(tradingApi, 'documents').mockImplementation(async (kind) => (
    kind === 'watchlist-flags' ? flagSets : watchlists
  ));
}

function watchlistCalls(documents: ReturnType<typeof mockDocuments>) {
  return documents.mock.calls.filter(([kind]) => kind === 'watchlists');
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
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
    mockDocuments([persisted]);
    const update = vi.spyOn(tradingApi, 'updateDocument');
    vi.spyOn(tradingApi, 'quote').mockResolvedValue(fixture({ price: '100' }));
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
    mockDocuments([record]);
    vi.spyOn(tradingApi, 'quote').mockResolvedValue(fixture({ price: '100' }));
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
    mockDocuments([otcRecord]);
    const quote = vi.spyOn(tradingApi, 'quote').mockResolvedValue(fixture({ price: '0.008' }));
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
    mockDocuments([record]);
    vi.spyOn(tradingApi, 'quote')
      .mockResolvedValueOnce(fixture({ price: '100' }))
      .mockImplementationOnce(() => refreshQuote.then((quote) => fixture(quote)));
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
    mockDocuments([orderedRecord]);
    vi.spyOn(tradingApi, 'quote').mockResolvedValue(fixture({ price: '100' }));
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
      {
        schemaVersion: 2,
        name: 'Default Watchlist',
        items: [
          { type: 'symbol', instrumentId: gameStop.instrument_id },
          { type: 'symbol', instrumentId: apple.instrument_id },
        ],
      },
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
    mockDocuments([sortableRecord]);
    vi.spyOn(tradingApi, 'quote').mockImplementation(async (instrumentId) => fixture(({
      price: instrumentId === gameStop.instrument_id ? '90' : '110',
    })));
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
    const documents = mockDocuments([twoSymbolRecord]);
    vi.spyOn(tradingApi, 'quote').mockResolvedValue(fixture({ price: '100' }));
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

    await waitFor(() => expect(update).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Select AAPL' })).not.toBeInTheDocument());
    expect(watchlistCalls(documents)).toHaveLength(3);
    expect(screen.getByText('saved')).toBeInTheDocument();
  });
});

function mockMarketData() {
  vi.spyOn(tradingApi, 'quote').mockResolvedValue(fixture({ price: '100' }));
  vi.spyOn(tradingApi, 'bars').mockResolvedValue({
    bars: [],
    binding: { supported_intervals: ['1m'] },
  } as unknown as BarsResponse);
}

function echoUpdates() {
  return vi.spyOn(tradingApi, 'updateDocument').mockImplementation(async (_kind, currentRecord, nextPayload) => ({
    ...currentRecord,
    revision: currentRecord.revision + 1,
    payload: nextPayload,
  }));
}

const sectionedRecord = {
  ...record,
  payload: {
    schemaVersion: 2,
    name: 'Sectioned',
    items: [
      { type: 'symbol', instrumentId: apple.instrument_id },
      { type: 'section', id: 'tech', name: 'Meme stocks', collapsed: false },
      { type: 'symbol', instrumentId: gameStop.instrument_id },
    ],
  },
} as unknown as TradingDocument;

const symbolNames = () => screen.getAllByRole('button', { name: /^Select / }).map((button) => button.querySelector('strong')?.textContent);

describe('TradingWatchlist sections and flags', () => {
  it('collapses a section, hides its symbols and keeps the state after a reload', async () => {
    mockDocuments([sectionedRecord]);
    mockMarketData();
    const update = echoUpdates();

    const view = render(
      <TradingWatchlist instruments={[apple, gameStop]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );

    await screen.findByRole('button', { name: 'Select GME' });
    expect(screen.getByRole('button', { name: 'Collapse section Meme stocks' })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Collapse section Meme stocks' }));

    await waitFor(() => expect(symbolNames()).toEqual(['AAPL']));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    const saved = update.mock.calls[0][2] as { items: Array<Record<string, unknown>> };
    expect(saved.items[1]).toEqual({ type: 'section', id: 'tech', name: 'Meme stocks', collapsed: true });

    view.unmount();
    mockDocuments([{ ...sectionedRecord, revision: 2, payload: saved } as unknown as TradingDocument]);
    render(
      <TradingWatchlist instruments={[apple, gameStop]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );
    expect(await screen.findByRole('button', { name: 'Expand section Meme stocks' })).toHaveAttribute('aria-expanded', 'false');
    expect(symbolNames()).toEqual(['AAPL']);
  });

  it('adds a named section from the options menu and upgrades a version 1 list on save', async () => {
    mockDocuments([record]);
    mockMarketData();
    const update = echoUpdates();
    vi.spyOn(window, 'prompt').mockReturnValue('Earnings');

    render(
      <TradingWatchlist instruments={[apple]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );

    await screen.findByRole('button', { name: 'Select AAPL' });
    fireEvent.click(screen.getByRole('button', { name: 'Watchlist options' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Add section' }));

    expect(await screen.findByRole('button', { name: 'Collapse section Earnings' })).toBeInTheDocument();
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0][2]).toEqual({
      schemaVersion: 2,
      name: 'Default Watchlist',
      items: [
        { type: 'symbol', instrumentId: apple.instrument_id },
        { type: 'section', id: expect.any(String), name: 'Earnings', collapsed: false },
      ],
    });
  });

  it('flags a symbol from its row and lists it under the generated flag list', async () => {
    const twoSymbols = { ...record, payload: { name: 'Default Watchlist', instrumentIds: [apple.instrument_id, gameStop.instrument_id] } } as unknown as TradingDocument;
    mockDocuments([twoSymbols]);
    mockMarketData();
    const create = vi.spyOn(tradingApi, 'createDocument').mockImplementation(async (kind, recordId, payload) => fixture({
      record_id: recordId,
      record_type: kind,
      revision: 1,
      payload,
      status: 'active',
    }));

    render(
      <TradingWatchlist instruments={[apple, gameStop]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );

    await screen.findByRole('button', { name: 'Select GME' });
    expect(screen.queryByRole('option', { name: 'Red flags' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Flag GME' }));
    fireEvent.click(within(screen.getByRole('menu', { name: 'Flag GME' })).getByRole('menuitemradio', { name: 'Red flag' }));

    await waitFor(() => expect(create).toHaveBeenCalledWith('watchlist-flags', 'default', {
      schemaVersion: 1,
      flags: [{ instrumentId: gameStop.instrument_id, color: 'red' }],
    }));
    expect(screen.getByRole('img', { name: 'Red flag' })).toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: 'Watchlist' }), { target: { value: 'flag:red' } });
    await waitFor(() => expect(symbolNames()).toEqual(['GME']));
    expect(screen.queryByRole('button', { name: 'Move GME up' })).not.toBeInTheDocument();
  });

  it('clears a flag when a symbol is removed from its flag list', async () => {
    const flagSet = fixture<TradingDocument>({
      record_id: 'default',
      record_type: 'watchlist_flag_set',
      revision: 4,
      payload: { schemaVersion: 1, flags: [{ instrumentId: apple.instrument_id, color: 'green' }] },
      status: 'active',
    });
    mockDocuments([record], [flagSet]);
    mockMarketData();
    const update = echoUpdates();

    render(
      <TradingWatchlist instruments={[apple]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );

    await screen.findByRole('option', { name: 'Green flags' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Watchlist' }), { target: { value: 'flag:green' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove AAPL' }));

    await waitFor(() => expect(update).toHaveBeenCalledWith('watchlist-flags', flagSet, { schemaVersion: 1, flags: [] }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Select AAPL' })).not.toBeInTheDocument());
  });
});

describe('TradingWatchlist columns', () => {
  it('adds a chosen column, sorts by it and remembers the view', async () => {
    const twoSymbols = { ...record, payload: { name: 'Default Watchlist', instrumentIds: [apple.instrument_id, gameStop.instrument_id] } } as unknown as TradingDocument;
    mockDocuments([twoSymbols]);
    vi.spyOn(tradingApi, 'quote').mockImplementation(async (instrumentId) => fixture({ price: instrumentId === apple.instrument_id ? '101' : '20' }));
    vi.spyOn(tradingApi, 'bars').mockImplementation(async (instrumentId) => ({
      bars: [{
        open: '100',
        close: '100',
        high: instrumentId === apple.instrument_id ? '102' : '25',
        low: '1',
        volume: instrumentId === apple.instrument_id ? '1000' : '5000000',
        session: 'regular',
        start_time: '2026-01-01T00:00:00Z',
      }],
      binding: { supported_intervals: ['1m'] },
    } as unknown as BarsResponse));

    const view = render(
      <TradingWatchlist instruments={[apple, gameStop]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );

    await screen.findByRole('button', { name: 'Select GME' });
    fireEvent.click(screen.getByRole('button', { name: 'Watchlist options' }));
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: /^Vol volume/ }));
    expect(screen.getByRole('menuitemcheckbox', { name: /^Vol volume/ })).toHaveAttribute('aria-checked', 'true');

    expect(await screen.findByText('5M')).toBeInTheDocument();
    expect(screen.getByText('1K')).toBeInTheDocument();
    await waitFor(() => expect(symbolNames()).toEqual(['AAPL', 'GME']));
    fireEvent.click(screen.getByRole('button', { name: 'Sort watchlist by volume descending' }));
    await waitFor(() => expect(symbolNames()).toEqual(['GME', 'AAPL']));
    fireEvent.click(screen.getByRole('button', { name: 'Sort watchlist by volume ascending' }));
    await waitFor(() => expect(symbolNames()).toEqual(['AAPL', 'GME']));

    view.unmount();
    render(
      <TradingWatchlist instruments={[apple, gameStop]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );
    expect(await screen.findByRole('button', { name: 'Clear watchlist volume sort' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Sort watchlist by symbol ascending' }));
    await waitFor(() => expect(symbolNames()).toEqual(['AAPL', 'GME']));
    expect(screen.getByRole('button', { name: 'Sort watchlist by symbol descending' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('hides a column and drops its sort', async () => {
    mockDocuments([record]);
    mockMarketData();
    window.localStorage.setItem('omnix.trading.watchlist-view', JSON.stringify({ columns: ['last', 'changePercent'], sort: { key: 'changePercent', direction: 'desc' } }));

    render(
      <TradingWatchlist instruments={[apple]} activeInstrumentId={apple.instrument_id} interval="1m" onSelect={vi.fn()} />,
    );

    await screen.findByRole('button', { name: 'Select AAPL' });
    fireEvent.click(screen.getByRole('button', { name: 'Watchlist options' }));
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: /^Chg% change percentage/ }));
    expect(screen.queryByRole('button', { name: /change percentage/ })).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem('omnix.trading.watchlist-view') ?? '{}')).toEqual({ columns: ['last'], sort: null });
  });
});
