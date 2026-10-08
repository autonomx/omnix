import { downloadBlob } from '../../shared/download';
import { binanceInstrumentIdFor } from './cryptoInstrumentDefaults';
import type { CanonicalInstrument } from './tradingTypes';
import {
  addWatchlistSection,
  addWatchlistSymbols,
  newWatchlistPayload,
  type WatchlistItem,
  type WatchlistPayload,
} from './tradingWatchlistModel';

/**
 * Watchlist text files (TVP-5.3): comma-separated `EXCHANGE:SYMBOL` tokens,
 * with `###Name` tokens starting a section. Line breaks are accepted as
 * separators on import.
 */
export type WatchlistTextEntry =
  | { type: 'section'; name: string }
  | { type: 'symbol'; token: string; exchange: string | null; symbol: string };

const SECTION_MARKER = '###';

export function parseWatchlistText(text: string): WatchlistTextEntry[] {
  return text
    .split(/[,\r\n]+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token): WatchlistTextEntry => {
      if (token.startsWith(SECTION_MARKER)) {
        return { type: 'section', name: token.slice(SECTION_MARKER.length).trim() || 'Section' };
      }
      const colon = token.indexOf(':');
      return {
        type: 'symbol',
        token,
        exchange: colon > 0 ? token.slice(0, colon).trim().toUpperCase() : null,
        symbol: (colon > 0 ? token.slice(colon + 1) : token).trim().toUpperCase(),
      };
    });
}

/** `VENUE:SYMBOL` for a listed instrument, from the catalog or, failing that, from its id. */
export function exchangeSymbolFor(instrumentId: string, instrument?: CanonicalInstrument): string {
  if (instrument) return `${instrument.venue}:${instrument.display_symbol}`;
  const parts = instrumentId.split(':');
  return parts.length >= 3 ? `${parts[1]}:${(parts.at(-1) ?? '').replace(/[-_/]/g, '')}` : instrumentId;
}

export function formatWatchlistText(items: readonly WatchlistItem[], symbolFor: (instrumentId: string) => string): string {
  return items
    .map((item) => item.type === 'section'
      ? `${SECTION_MARKER}${item.name.replace(/[,\r\n]+/g, ' ')}`
      : symbolFor(item.instrumentId))
    .join(',');
}

export function downloadWatchlistText(name: string, text: string): void {
  const fileName = name.replace(/[\\/:*?"<>|]+/g, '-').trim() || 'watchlist';
  downloadBlob(new Blob([text], { type: 'text/plain' }), `${fileName}.txt`);
}

function symbolMatches(instrument: CanonicalInstrument, exchange: string | null, symbol: string): boolean {
  if (exchange && instrument.venue.toUpperCase() !== exchange) return false;
  return [instrument.display_symbol, instrument.venue_symbol, instrument.venue_symbol.replace(/[-_/]/g, '')]
    .some((candidate) => candidate.toUpperCase() === symbol);
}

function findInstrument(
  instruments: readonly CanonicalInstrument[],
  entry: Extract<WatchlistTextEntry, { type: 'symbol' }>,
): CanonicalInstrument | undefined {
  const exact = instruments.find((instrument) => instrument.instrument_id === entry.token);
  if (exact) return exact;
  const matches = instruments.filter((instrument) => symbolMatches(instrument, entry.exchange, entry.symbol));
  // `BINANCE:BTCUSDT` names spot and perpetual alike; spot is the default.
  return matches.find((instrument) => instrument.instrument_type !== 'perpetual') ?? matches[0];
}

export type WatchlistImportResult = {
  payload: WatchlistPayload;
  /** Instruments found through search, for the caller's catalog. */
  instruments: CanonicalInstrument[];
  unresolved: string[];
};

const SEARCH_BATCH = 5;

/**
 * Build a new watchlist from a text file. Symbols missing from `catalog` are
 * looked up with `search`, a few at a time and at most `maxSearches`
 * symbols; the rest are reported as unresolved.
 */
export async function importWatchlistText(
  name: string,
  text: string,
  catalog: readonly CanonicalInstrument[],
  search: (query: string) => Promise<CanonicalInstrument[]>,
  maxSearches = 50,
): Promise<WatchlistImportResult> {
  const entries = parseWatchlistText(text);
  const known = [...catalog];
  const found: CanonicalInstrument[] = [];
  const missing = [...new Map(entries
    .filter((entry): entry is Extract<WatchlistTextEntry, { type: 'symbol' }> => entry.type === 'symbol')
    .filter((entry) => !findInstrument(known, entry))
    .map((entry) => [entry.symbol, entry])).values()].slice(0, maxSearches);
  for (let index = 0; index < missing.length; index += SEARCH_BATCH) {
    const results = await Promise.all(missing.slice(index, index + SEARCH_BATCH).map((entry) => search(entry.symbol).catch(() => [])));
    for (const result of results) {
      known.push(...result);
      found.push(...result);
    }
  }

  let payload = newWatchlistPayload(name);
  const used: CanonicalInstrument[] = [];
  const unresolved: string[] = [];
  for (const entry of entries) {
    if (entry.type === 'section') {
      payload = addWatchlistSection(payload, entry.name);
      continue;
    }
    const instrument = findInstrument(known, entry);
    if (!instrument) {
      unresolved.push(entry.token);
      continue;
    }
    if (found.includes(instrument) && !used.includes(instrument)) used.push(instrument);
    payload = addWatchlistSymbols(payload, [binanceInstrumentIdFor(instrument.instrument_id)]);
  }
  return { payload, instruments: used, unresolved };
}
