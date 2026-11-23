import { useEffect, useRef, useState } from 'react';
import { dateInputValue, tradingDateRangeWithinLoadedHistory, zonedDateTimeToUtc } from './tradingTime';
import { CustomVisibleRange, TradingChartPanelProps, applyVisibleRange } from './tradingChartPanelModel';
import type { useChartPanelState } from './useTradingChartPanelState';
import type { useChartPanelData } from './useTradingChartPanelData';

/** What the custom range reads from the rest of the panel: the chart, its bars and the visible-range choice. */
export type ChartCustomRangeInput = Pick<TradingChartPanelProps, 'interval'>
  & Pick<ReturnType<typeof useChartPanelState>, 'adapterRef' | 'barsRef' | 'rightOffset' | 'selectedRangeRef' | 'setSelectedRangeLabel' | 'setTimezoneMenuOpen'>
  & Pick<ReturnType<typeof useChartPanelData>, 'selectedTimezone'>;

/** The footer's custom date range: its popover, the chosen dates and why they were refused. */
export function useChartCustomRange(input: ChartCustomRangeInput) {
  const {
    adapterRef, barsRef, interval, rightOffset, selectedRangeRef, selectedTimezone, setSelectedRangeLabel,
    setTimezoneMenuOpen,
  } = input;
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && !ref.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside, true);
    return () => document.removeEventListener('pointerdown', closeOutside, true);
  }, [open]);

  /** Opens the popover on the loaded history's first and last dates (keeping any already chosen), or closes it. */
  const toggle = () => {
    const first = barsRef.current[0]?.start_time ?? new Date().toISOString();
    const last = barsRef.current.at(-1)?.end_time ?? new Date().toISOString();
    setStart((current) => current || dateInputValue(first, selectedTimezone));
    setEnd((current) => current || dateInputValue(last, selectedTimezone));
    setError(null);
    setOpen((current) => !current);
    setTimezoneMenuOpen(false);
  };

  const close = () => setOpen(false);

  /** Shows the chosen dates when they are in order and inside the loaded history; otherwise says why not. */
  const apply = () => {
    const fromTime = zonedDateTimeToUtc(start, selectedTimezone);
    const toTime = zonedDateTimeToUtc(end, selectedTimezone, true);
    if (fromTime === null || toTime === null) {
      setError('Choose both a start and end date.');
      return;
    }
    if (fromTime > toTime) {
      setError('The start date must be before the end date.');
      return;
    }
    const firstLoaded = barsRef.current[0]?.start_time;
    const lastLoaded = barsRef.current.at(-1)?.end_time ?? barsRef.current.at(-1)?.start_time;
    if (!firstLoaded || !lastLoaded) {
      setError('No chart history is loaded for this range.');
      return;
    }
    if (!tradingDateRangeWithinLoadedHistory(start, end, firstLoaded, lastLoaded, selectedTimezone)) {
      setError(
        `Requested dates are outside loaded history (${dateInputValue(firstLoaded, selectedTimezone)} to ${dateInputValue(lastLoaded, selectedTimezone)}).`,
      );
      return;
    }
    const selection = { from: start, to: end } satisfies CustomVisibleRange;
    selectedRangeRef.current = selection;
    setSelectedRangeLabel('Custom');
    setError(null);
    setOpen(false);
    const chart = adapterRef.current?.api();
    if (chart) applyVisibleRange(chart, selection, barsRef.current, interval, rightOffset, selectedTimezone);
  };

  return { customRange: { open, start, end, error, ref, setStart, setEnd, toggle, close, apply } };
}

export type ChartCustomRange = ReturnType<typeof useChartCustomRange>['customRange'];
