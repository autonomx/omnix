import { describe, expect, it, vi } from 'vitest';
import type { CanonicalInstrument } from './tradingTypes';
import {
  exchangeSymbolFor,
  formatWatchlistText,
  importWatchlistText,
  parseWatchlistText,
} from './tradingWatchlistTransfer';

function instrument(instrumentId: string, venue: string, displaySymbol: string, venueSymbol = displaySymbol, type = 'equity'): CanonicalInstrument {
  return {
    instrument_id: instrumentId,
    asset_class: type === 'equity' ? 'equity' : 'crypto',
    instrument_type: type,
    venue,
    venue_symbol: venueSymbol,
    display_symbol: displaySymbol,
    base_currency: null,
    quote_currency: 'USD',
    exchange_timezone: 'UTC',
    session_calendar: '24x7',
    price_scale: 100,
    minimum_tick: '0.01',
    status: 'active',
  } as CanonicalInstrument;
}

const apple = instrument('equity:NASDAQ:AAPL', 'NASDAQ', 'AAPL');
const btcSpot = instrument('crypto:BINANCE:spot:BTC-USDT', 'BINANCE', 'BTCUSDT', 'BTC-USDT', 'spot');
const btcPerp = instrument('crypto:BINANCE:perpetual:BTC-USDT', 'BINANCE', 'BTCUSDT', 'BTC-USDT', 'perpetual');

describe('watchlist text files', () => {
  it('parses symbols and section markers separated by commas or lines', () => {
    expect(parseWatchlistText('###Tech, NASDAQ:aapl,\nTSLA\r\n###  ,BINANCE:BTCUSDT,,')).toEqual([
      { type: 'section', name: 'Tech' },
      { type: 'symbol', token: 'NASDAQ:aapl', exchange: 'NASDAQ', symbol: 'AAPL' },
      { type: 'symbol', token: 'TSLA', exchange: null, symbol: 'TSLA' },
      { type: 'section', name: 'Section' },
      { type: 'symbol', token: 'BINANCE:BTCUSDT', exchange: 'BINANCE', symbol: 'BTCUSDT' },
    ]);
  });

  it('exports sections and EXCHANGE:SYMBOL tokens in list order', () => {
    const text = formatWatchlistText([
      { type: 'symbol', instrumentId: apple.instrument_id },
      { type: 'section', id: 's', name: 'Crypto, majors', collapsed: true },
      { type: 'symbol', instrumentId: btcSpot.instrument_id },
      { type: 'symbol', instrumentId: 'equity:NYSE:BRK-B' },
    ], (instrumentId) => exchangeSymbolFor(instrumentId, [apple, btcSpot].find((item) => item.instrument_id === instrumentId)));
    expect(text).toBe('NASDAQ:AAPL,###Crypto  majors,BINANCE:BTCUSDT,NYSE:BRKB');
  });

  it('round-trips an exported list through import', async () => {
    const search = vi.fn(async () => []);
    const result = await importWatchlistText('Copy', 'NASDAQ:AAPL,###Crypto,BINANCE:BTCUSDT', [apple, btcPerp, btcSpot], search);
    expect(result.payload).toEqual({
      schemaVersion: 2,
      name: 'Copy',
      items: [
        { type: 'symbol', instrumentId: apple.instrument_id },
        { type: 'section', id: expect.any(String), name: 'Crypto', collapsed: false },
        { type: 'symbol', instrumentId: btcSpot.instrument_id },
      ],
    });
    expect(result.unresolved).toEqual([]);
    expect(search).not.toHaveBeenCalled();
  });

  it('searches for unknown symbols once each and reports the ones it cannot find', async () => {
    const msft = instrument('equity:NASDAQ:MSFT', 'NASDAQ', 'MSFT');
    const search = vi.fn(async (query: string) => (query === 'MSFT' ? [msft] : []));
    const result = await importWatchlistText('Mixed', 'NASDAQ:MSFT,NASDAQ:MSFT,NYSE:MSFT,LSE:NOPE,equity:NASDAQ:AAPL', [apple], search);
    expect(search.mock.calls.map(([query]) => query)).toEqual(['MSFT', 'NOPE']);
    expect(result.payload.items).toEqual([
      { type: 'symbol', instrumentId: msft.instrument_id },
      { type: 'symbol', instrumentId: apple.instrument_id },
    ]);
    expect(result.instruments).toEqual([msft]);
    expect(result.unresolved).toEqual(['NYSE:MSFT', 'LSE:NOPE']);
  });
});
