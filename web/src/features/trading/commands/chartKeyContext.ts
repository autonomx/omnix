/**
 * Whether the chart area has the keyboard.
 *
 * Plain chart keys (letters, digits, arrows) would take keys from other parts
 * of the page, so they fire only while the chart area has the keyboard:
 * - `chart`: nothing else has focus (or focus is inside the chart area), and
 *   the last click was not outside the chart area. This holds when the page
 *   opens, so typing a symbol works straight away.
 * - `chartClicked`: the last click was in the chart area and nothing has
 *   focus. Tab needs this stricter rule so keyboard users still move focus
 *   into the page with it.
 */
export type ChartKeyContext = 'chart' | 'chartClicked';

/** The chart grid's container in the trading workspace. */
export const CHART_AREA_SELECTOR = '.trading-chart-shell';

let lastPointer: 'none' | 'chart' | 'outside' = 'none';

export function noteTradingPointerDown(target: EventTarget | null): void {
  lastPointer = target instanceof Element && target.closest(CHART_AREA_SELECTOR) ? 'chart' : 'outside';
}

/** For tests and when the workspace unmounts. */
export function resetTradingPointerContext(): void {
  lastPointer = 'none';
}

export function chartKeyContextActive(context: ChartKeyContext, event?: Event): boolean {
  const target = event?.target instanceof Node ? event.target : null;
  const owner = target?.ownerDocument ?? (typeof document === 'undefined' ? null : document);
  const focused = owner?.activeElement ?? null;
  const nothingFocused = focused === null || focused === owner?.body;
  if (context === 'chartClicked') return lastPointer === 'chart' && nothingFocused;
  return lastPointer !== 'outside' && (nothingFocused || focused?.closest(CHART_AREA_SELECTOR) != null);
}
