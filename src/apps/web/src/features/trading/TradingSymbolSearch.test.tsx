import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { TradingSymbolSearch } from './TradingSymbolSearch';
import type { CanonicalInstrument } from './tradingTypes';

const crypto: CanonicalInstrument = {
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  asset_class: 'crypto',
  instrument_type: 'spot',
  venue: 'BINANCE',
  venue_symbol: 'BTC-USDT',
  display_symbol: 'BTCUSDT',
  base_currency: 'BTC',
  quote_currency: 'USDT',
  exchange_timezone: 'UTC',
  session_calendar: '24x7',
  price_scale: 100,
  minimum_tick: '0.01',
  status: 'active',
};

const stock: CanonicalInstrument = {
  instrument_id: 'equity:NASDAQ:AAPL',
  asset_class: 'equity',
  instrument_type: 'equity',
  venue: 'NASDAQ',
  venue_symbol: 'AAPL',
  display_symbol: 'AAPL',
  base_currency: null,
  quote_currency: 'USD',
  exchange_timezone: 'America/New_York',
  session_calendar: 'XNYS',
  price_scale: 100,
  minimum_tick: '0.01',
  status: 'active',
};

function SearchHarness({ onSelect, onClose }: { onSelect: (instrument: CanonicalInstrument) => void; onClose: () => void }) {
  const [query, setQuery] = useState('');
  return (
    <TradingSymbolSearch
      open
      query={query}
      instruments={[crypto, stock]}
      activeInstrumentId={crypto.instrument_id}
      onQueryChange={setQuery}
      onSelect={onSelect}
      onClose={onClose}
    />
  );
}

describe('TradingSymbolSearch', () => {
  it('opens with TradingView-style categories and filters stock and crypto rows', () => {
    render(<SearchHarness onSelect={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByRole('dialog', { name: 'Symbol search' })).toBeVisible();
    expect(screen.getByRole('button', { name: /BTCUSDT/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /AAPL/ })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Stocks' }));
    expect(screen.getByRole('button', { name: /AAPL/ })).toBeVisible();
    expect(screen.queryByRole('button', { name: /BTCUSDT/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Crypto' }));
    expect(screen.getByRole('button', { name: /BTCUSDT/ })).toBeVisible();
    expect(screen.queryByRole('button', { name: /AAPL/ })).not.toBeInTheDocument();
  });

  it('searches by query and selects a result', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(<SearchHarness onSelect={onSelect} onClose={onClose} />);

    fireEvent.change(screen.getByRole('textbox', { name: 'Search symbols' }), { target: { value: 'AAP' } });
    expect(screen.getByRole('button', { name: /AAPL/ })).toBeVisible();
    expect(screen.queryByRole('button', { name: /BTCUSDT/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /AAPL/ }));
    expect(onSelect).toHaveBeenCalledWith(stock);

    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Search symbols' }), { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
