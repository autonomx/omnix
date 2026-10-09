/**
 * Indicator on indicator (TVP-6.5): an indicator computed on another chart indicator's output (SMA of RSI, RSI of OBV).
 *
 * The source output becomes bars whose open, high, low and close are its value (times and volume kept), on the bars
 * where it has a finite value, and the indicator runs on those bars. Only indicators that read the close alone take a
 * source, so the result is the indicator of the source series. The server alert evaluator does the same
 * (`indicators/sources.py`); the shared fixture `indicator_goldens/sources.json` proves they agree.
 */
import type { MarketBar } from '../tradingTypes';
import type { CoreIndicatorInstance, IndicatorOutput } from './coreIndicators';

/** An indicator's source: another indicator on the chart (by id; one instance per id) and one of its outputs. */
export type IndicatorSourceRef = { indicatorId: string; output: string };

/** The ids whose indicator reads only the close; `SOURCE_TARGET_IDS` in indicators/sources.py lists the same. */
export const SOURCE_TARGET_IDS: readonly string[] = [
  'sma', 'ema', 'rsi', 'macd', 'bollinger', 'stochastic-rsi',
  'tv-arnaud-legoux-moving-average', 'tv-chande-momentum-oscillator-cmo', 'tv-connors-rsi-crsi', 'tv-coppock-curve',
  'tv-detrended-price-oscillator-dpo', 'tv-double-exponential-moving-average-ema', 'tv-historical-volatility',
  'tv-hull-moving-average', 'tv-know-sure-thing-kst', 'tv-mcginley-dynamic', 'tv-momentum', 'tv-moving-average-ribbon',
  'tv-moving-averages', 'tv-price-momentum-oscillator-pmo', 'tv-rci-ribbon', 'tv-rate-of-change-roc',
  'tv-relative-volatility-index', 'tv-smi-ergodic-oscillator', 'tv-smoothed-moving-average', 'tv-trix',
  'tv-trend-strength-index', 'tv-triple-ema', 'tv-true-strength-index', 'tv-weighted-moving-average',
];
const TARGETS = new Set(SOURCE_TARGET_IDS);

export function acceptsIndicatorSource(id: string): boolean {
  return TARGETS.has(id);
}

/** The bars an output's values make: open, high, low and close all the value, on the bars where it is finite. */
export function sourceBars(bars: readonly MarketBar[], points: IndicatorOutput['points']): MarketBar[] {
  const values = new Map(points.filter((point) => Number.isFinite(point.value)).map((point) => [point.time, point.value]));
  return bars.flatMap((bar) => {
    const value = values.get(bar.start_time);
    if (value === undefined) return [];
    const price = String(value);
    return [{ ...bar, open: price, high: price, low: price, close: price }];
  });
}

/**
 * The indicators in the order they compute, sources first, each with a source it can use: a target that takes one,
 * reading an enabled indicator computed with it (`computable`) that has no source of its own. Any other source,
 * including a cycle, is dropped and the indicator reads the close.
 */
export function orderBySources(indicators: readonly CoreIndicatorInstance[], computable: (indicator: CoreIndicatorInstance) => boolean = () => true): CoreIndicatorInstance[] {
  const byId = new Map(indicators.map((indicator) => [String(indicator.id), indicator]));
  const resolved = indicators.map((indicator) => {
    const source = indicator.source;
    if (!source) return indicator;
    const target = byId.get(source.indicatorId);
    const usable = acceptsIndicatorSource(String(indicator.id)) && target !== undefined && target !== indicator
      && target.enabled && !target.source && computable(target);
    return usable ? indicator : { ...indicator, source: null };
  });
  // One level deep: sources (no source of their own) first, then the indicators that read them.
  return [...resolved.filter((indicator) => !indicator.source), ...resolved.filter((indicator) => indicator.source)];
}

/**
 * Computes indicators in source order. `raw` gives an indicator's unstyled outputs on bars; `style` applies its style
 * (and may hide plots). A source is read from the raw outputs, so a hidden plot can still feed another indicator; the
 * reading indicator's outputs are drawn in the source's pane.
 */
export function calculateWithSources(
  bars: readonly MarketBar[],
  indicators: readonly CoreIndicatorInstance[],
  raw: (bars: readonly MarketBar[], indicator: CoreIndicatorInstance) => IndicatorOutput[],
  style: (outputs: IndicatorOutput[], indicator: CoreIndicatorInstance) => IndicatorOutput[] = (outputs) => outputs,
): IndicatorOutput[] {
  const computed = new Map<string, IndicatorOutput>();
  return orderBySources(indicators).flatMap((indicator) => {
    let outputs: IndicatorOutput[];
    if (indicator.source) {
      const { indicatorId, output } = indicator.source;
      // The key carries the source's inputs (rsi:14); after they change, its first line stands in.
      const source = computed.get(output) ?? [...computed.values()].find((item) => item.key.split(':', 1)[0] === indicatorId);
      if (!source) return [];
      outputs = raw(sourceBars(bars, source.points), indicator).map((output) => (
        source.pane === 1 ? { ...output, pane: 1 as const, paneOf: source.paneOf ?? source.key.split(':', 1)[0] } : { ...output, pane: 0 as const }
      ));
    } else {
      outputs = raw(bars, indicator);
    }
    for (const output of outputs) computed.set(output.key, output);
    return style(outputs, indicator);
  });
}

/** The outputs an indicator can read on this chart: the other enabled indicators' lines, when it takes a source. */
export function indicatorSourceChoices(
  indicator: CoreIndicatorInstance,
  indicators: readonly CoreIndicatorInstance[],
  outputs: readonly IndicatorOutput[],
): Array<{ value: string; label: string; ref: IndicatorSourceRef }> {
  if (!acceptsIndicatorSource(String(indicator.id))) return [];
  const others = new Set(indicators.filter((item) => item.id !== indicator.id && item.enabled && !item.source).map((item) => String(item.id)));
  return outputs.flatMap((output) => {
    const indicatorId = output.key.split(':', 1)[0];
    if (!others.has(indicatorId) || output.kind !== 'line' && output.kind !== 'histogram') return [];
    return [{ value: output.key, label: output.title, ref: { indicatorId, output: output.key } }];
  });
}
