import { useRef, useState, type ChangeEvent } from 'react';
import { tradingApi } from './tradingApi';
import type { CanonicalInstrument } from './tradingTypes';
import { watchlistSymbolIds, type WatchlistPayload } from './tradingWatchlistModel';
import { importWatchlistText } from './tradingWatchlistTransfer';

function importNotice(count: number, unresolved: readonly string[]): string {
  const imported = `Imported ${count} ${count === 1 ? 'symbol' : 'symbols'}`;
  if (unresolved.length === 0) return `${imported}.`;
  const shown = unresolved.slice(0, 10).join(', ');
  return `${imported}; not found: ${shown}${unresolved.length > 10 ? ` and ${unresolved.length - 10} more` : ''}.`;
}

/**
 * Import a `.txt` watchlist file (TVP-5.3) as a new watchlist named after the
 * file. `notice` reports the result, including symbols that were not found.
 */
export function useTradingWatchlistImport({
  catalog,
  create,
  onInstrumentsFound,
}: {
  catalog: readonly CanonicalInstrument[];
  create: (payload: WatchlistPayload) => Promise<boolean>;
  onInstrumentsFound: (instruments: CanonicalInstrument[]) => void;
}) {
  const [notice, setNotice] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const importFile = async (file: File) => {
    setNotice(`Importing ${file.name}…`);
    try {
      const result = await importWatchlistText(
        file.name.replace(/\.txt$/i, '').trim() || 'Imported watchlist',
        await file.text(),
        catalog,
        (query) => tradingApi.instruments(query),
      );
      onInstrumentsFound(result.instruments);
      const created = await create(result.payload);
      setNotice(created
        ? importNotice(watchlistSymbolIds(result.payload).length, result.unresolved)
        : 'The imported watchlist could not be saved.');
    } catch {
      setNotice('The watchlist file could not be read.');
    }
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Clearing the value lets the same file be imported again.
    event.target.value = '';
    if (file) void importFile(file);
  };

  return { notice, inputRef, onInputChange, openFilePicker: () => inputRef.current?.click() };
}
