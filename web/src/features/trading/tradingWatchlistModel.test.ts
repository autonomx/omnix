import { describe, expect, it } from 'vitest';
import {
  addWatchlistSection,
  addWatchlistSymbols,
  flagListColor,
  flagListId,
  flaggedInstrumentIds,
  moveWatchlistItem,
  readWatchlistFlags,
  removeWatchlistSection,
  setWatchlistFlags,
  upgradeWatchlistPayload,
  watchlistRows,
  watchlistSymbolIds,
  watchlistSymbolsNeedRewrite,
  type WatchlistPayload,
} from './tradingWatchlistModel';

const AAPL = 'equity:NASDAQ:AAPL';
const GME = 'equity:NYSE:GME';
const TSLA = 'equity:NASDAQ:TSLA';

const sectioned: WatchlistPayload = {
  schemaVersion: 2,
  name: 'List',
  items: [
    { type: 'symbol', instrumentId: AAPL },
    { type: 'section', id: 's1', name: 'Movers', collapsed: false },
    { type: 'symbol', instrumentId: GME },
    { type: 'symbol', instrumentId: TSLA },
  ],
};

describe('watchlist payload upgrade', () => {
  it('reads a version 1 payload as ordered symbol items', () => {
    expect(upgradeWatchlistPayload({ name: 'Old', instrumentIds: [AAPL, GME, AAPL, 7] })).toEqual({
      schemaVersion: 2,
      name: 'Old',
      items: [
        { type: 'symbol', instrumentId: AAPL },
        { type: 'symbol', instrumentId: GME },
      ],
    });
  });

  it('normalises legacy crypto ids and drops malformed items', () => {
    const upgraded = upgradeWatchlistPayload({
      schemaVersion: 2,
      name: 'Crypto',
      items: [
        { type: 'symbol', instrumentId: 'crypto:COINBASE:spot:BTC-USD' },
        { type: 'section', id: 's1', name: '  ', collapsed: 'yes' },
        { type: 'chart' },
        null,
      ],
    });
    expect(upgraded.items).toEqual([
      { type: 'symbol', instrumentId: 'crypto:BINANCE:spot:BTC-USDT' },
      { type: 'section', id: 's1', name: 'Section', collapsed: false },
    ]);
  });

  it('reports when reading changed the stored symbols', () => {
    expect(watchlistSymbolsNeedRewrite({ instrumentIds: [AAPL] })).toBe(false);
    expect(watchlistSymbolsNeedRewrite({ instrumentIds: [AAPL, AAPL] })).toBe(true);
    expect(watchlistSymbolsNeedRewrite({ instrumentIds: ['crypto:KRAKEN:spot:ETH-USD'] })).toBe(true);
  });

  it('falls back to an empty, named list for unreadable payloads', () => {
    expect(upgradeWatchlistPayload(undefined)).toEqual({ schemaVersion: 2, name: 'Watchlist', items: [] });
  });
});

describe('watchlist items', () => {
  it('does not add a symbol twice', () => {
    expect(watchlistSymbolIds(addWatchlistSymbols(sectioned, [GME, 'equity:NYSE:F']))).toEqual([AAPL, GME, TSLA, 'equity:NYSE:F']);
  });

  it('inserts a section before a symbol or at the end', () => {
    expect(addWatchlistSection(sectioned, 'Watch', TSLA, 'new').items.map((item) => item.type === 'section' ? item.name : item.instrumentId))
      .toEqual([AAPL, 'Movers', GME, 'Watch', TSLA]);
    expect(addWatchlistSection(sectioned, 'Last', null, 'new').items.at(-1)).toEqual({ type: 'section', id: 'new', name: 'Last', collapsed: false });
  });

  it('moves a symbol across a header into the neighbouring section', () => {
    const moved = moveWatchlistItem(sectioned, 2, -1);
    expect(watchlistRows(moved.items).map((row) => row.kind === 'symbol' ? `${row.instrumentId}@${row.sectionId}` : row.section.name))
      .toEqual([`${AAPL}@null`, `${GME}@null`, 'Movers', `${TSLA}@s1`]);
    expect(moveWatchlistItem(sectioned, 0, -1)).toBe(sectioned);
  });

  it('keeps the symbols of a removed section', () => {
    expect(watchlistSymbolIds(removeWatchlistSection(sectioned, 's1'))).toEqual([AAPL, GME, TSLA]);
  });
});

describe('watchlist rows', () => {
  it('hides the symbols of a collapsed section and counts them', () => {
    const collapsed = { ...sectioned, items: sectioned.items.map((item) => item.type === 'section' ? { ...item, collapsed: true } : item) };
    expect(watchlistRows(collapsed.items)).toEqual([
      { kind: 'symbol', instrumentId: AAPL, itemIndex: 0, sectionId: null },
      { kind: 'section', section: { type: 'section', id: 's1', name: 'Movers', collapsed: true }, itemIndex: 1, symbolCount: 2 },
    ]);
  });

  it('sorts within each section only', () => {
    const order = [TSLA, GME, AAPL];
    const rows = watchlistRows(sectioned.items, (left, right) => order.indexOf(left) - order.indexOf(right));
    expect(rows.map((row) => row.kind === 'symbol' ? row.instrumentId : row.section.id)).toEqual([AAPL, 's1', TSLA, GME]);
  });
});

describe('watchlist flags', () => {
  it('keeps one flag per symbol and preserves flag order when recoloured', () => {
    let flags = readWatchlistFlags({ schemaVersion: 1, flags: [{ instrumentId: AAPL, color: 'red' }, { instrumentId: AAPL, color: 'blue' }, { instrumentId: GME, color: 'pink' }] });
    expect(flags.flags).toEqual([{ instrumentId: AAPL, color: 'red' }]);
    flags = setWatchlistFlags(flags, [GME, TSLA], 'red');
    flags = setWatchlistFlags(flags, [AAPL], 'green');
    expect(flaggedInstrumentIds(flags, 'red')).toEqual([GME, TSLA]);
    expect(flaggedInstrumentIds(flags, 'green')).toEqual([AAPL]);
    expect(setWatchlistFlags(flags, [GME], null).flags.map((flag) => flag.instrumentId)).toEqual([AAPL, TSLA]);
  });

  it('round-trips generated flag list ids', () => {
    expect(flagListColor(flagListId('purple'))).toBe('purple');
    expect(flagListColor('flag:pink')).toBeNull();
    expect(flagListColor('default')).toBeNull();
  });
});
