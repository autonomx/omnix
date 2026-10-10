import { useEffect, useMemo, useState } from 'react';
import { tradingApi } from './tradingApi';
import { indicatorColumnLine, isIndicatorColumnId, type WatchlistColumnId, type WatchlistSnapshot } from './tradingWatchlistColumns';

/** How often indicator columns refresh while the watchlist is shown. */
export const INDICATOR_COLUMNS_REFRESH_MS = 60_000;
/** Symbols one request carries (the server's limit). */
const MAX_SYMBOLS = 200;

export type WatchlistIndicatorValues = Readonly<Record<string, Readonly<Record<string, number | null>>>>;

/**
 * The watchlist's indicator column values (TVP-5.2), by symbol and column id, from the server, refreshed every
 * minute. Empty while there are no indicator columns.
 */
export function useWatchlistIndicatorValues(instrumentIds: readonly string[], interval: string, columnIds: readonly WatchlistColumnId[]): WatchlistIndicatorValues {
  const columns = useMemo(() => columnIds.filter(isIndicatorColumnId), [columnIds]);
  const symbols = useMemo(() => instrumentIds.slice(0, MAX_SYMBOLS), [instrumentIds]);
  const key = JSON.stringify([symbols, interval, columns]);
  const [values, setValues] = useState<WatchlistIndicatorValues>({});

  useEffect(() => {
    if (columns.length === 0 || symbols.length === 0) {
      setValues({});
      return undefined;
    }
    let cancelled = false;
    const lines = columns.flatMap((id) => {
      const line = indicatorColumnLine(id);
      return line ? [{ id, indicator_id: line.indicatorId, period: line.period, output: line.output }] : [];
    });
    const load = () => {
      void tradingApi.indicatorValues(symbols, interval, lines).then((rows) => {
        if (cancelled) return;
        setValues(Object.fromEntries(Object.entries(rows).map(([instrumentId, row]) => [
          instrumentId,
          Object.fromEntries(lines.map((line, index) => {
            const value = row[index] == null ? null : Number(row[index]);
            return [line.id, value != null && Number.isFinite(value) ? value : null];
          })),
        ])));
      }).catch(() => undefined); // keep the last values; the next refresh tries again
    };
    load();
    const timer = window.setInterval(load, INDICATOR_COLUMNS_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // `key` stands for symbols, interval and columns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return values;
}

/** The watchlist's snapshots with their indicator column values joined in, so cells and sorting treat them alike. */
export function useWatchlistSnapshotsWithIndicators(
  snapshots: Readonly<Record<string, WatchlistSnapshot>>,
  instrumentIds: readonly string[],
  interval: string,
  columnIds: readonly WatchlistColumnId[],
): Readonly<Record<string, WatchlistSnapshot>> {
  const values = useWatchlistIndicatorValues(instrumentIds, interval, columnIds);
  return useMemo(() => {
    if (Object.keys(values).length === 0) return snapshots;
    const ids = new Set([...Object.keys(snapshots), ...Object.keys(values)]);
    return Object.fromEntries([...ids].map((id) => [id, { ...(id in snapshots ? snapshots[id] : { price: null, changePercent: null }), indicators: values[id] }]));
  }, [snapshots, values]);
}
