import type { MarketBar } from '../tradingTypes';

export const CORE_INDICATOR_FORMULA_VERSION = 'omnix-indicators-v2';

export type IndicatorPoint = { time: string; value: number };
export type IndicatorOutput = {
  key: string;
  title: string;
  pane: 0 | 1;
  kind: 'line' | 'histogram';
  points: IndicatorPoint[];
};
export type CoreIndicatorId = 'sma' | 'ema' | 'rsi' | 'macd' | 'bollinger' | 'atr' | 'vwap';
export type CoreIndicatorInstance = {
  id: CoreIndicatorId;
  period: number;
  enabled: boolean;
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  standardDeviations?: number;
  anchorTime?: string | null;
};

export function indicatorUsesSeparatePane(id: CoreIndicatorId): boolean {
  return id === 'rsi' || id === 'macd' || id === 'atr';
}

function closes(bars: readonly MarketBar[]): number[] {
  return bars.map((bar) => Number(bar.close));
}

function validatePeriod(period: number): void {
  if (!Number.isInteger(period) || period < 1) throw new Error('Indicator period must be a positive integer');
}

export function simpleMovingAverage(values: readonly number[], period: number): number[] {
  validatePeriod(period);
  if (values.length < period) return [];
  let sum = values.slice(0, period).reduce((total, value) => total + value, 0);
  const result = [sum / period];
  for (let index = period; index < values.length; index += 1) {
    sum += values[index] - values[index - period];
    result.push(sum / period);
  }
  return result;
}

export function exponentialMovingAverage(values: readonly number[], period: number): number[] {
  validatePeriod(period);
  if (values.length < period) return [];
  let average = values.slice(0, period).reduce((total, value) => total + value, 0) / period;
  const multiplier = 2 / (period + 1);
  const result = [average];
  for (const value of values.slice(period)) {
    average = (value - average) * multiplier + average;
    result.push(average);
  }
  return result;
}

export function relativeStrengthIndex(values: readonly number[], period: number): number[] {
  validatePeriod(period);
  if (values.length <= period) return [];
  const gains: number[] = [];
  const losses: number[] = [];
  for (let index = 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    gains.push(Math.max(change, 0));
    losses.push(Math.max(-change, 0));
  }
  let averageGain = gains.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  let averageLoss = losses.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  const value = () => averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss);
  const result = [value()];
  for (let index = period; index < gains.length; index += 1) {
    averageGain = (averageGain * (period - 1) + gains[index]) / period;
    averageLoss = (averageLoss * (period - 1) + losses[index]) / period;
    result.push(value());
  }
  return result;
}

export function bollingerBands(
  values: readonly number[],
  period: number,
  standardDeviations = 2,
): Array<{ middle: number; upper: number; lower: number }> {
  validatePeriod(period);
  if (!Number.isFinite(standardDeviations) || standardDeviations <= 0) throw new Error('Bollinger deviation must be positive');
  if (values.length < period) return [];
  const result: Array<{ middle: number; upper: number; lower: number }> = [];
  for (let index = period - 1; index < values.length; index += 1) {
    const window = values.slice(index - period + 1, index + 1);
    const middle = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce((sum, value) => sum + (value - middle) ** 2, 0) / period;
    const deviation = Math.sqrt(variance) * standardDeviations;
    result.push({ middle, upper: middle + deviation, lower: middle - deviation });
  }
  return result;
}

export function averageTrueRange(
  highs: readonly number[],
  lows: readonly number[],
  closeValues: readonly number[],
  period: number,
): number[] {
  validatePeriod(period);
  if (highs.length !== lows.length || highs.length !== closeValues.length) throw new Error('ATR inputs must have equal length');
  const ranges = highs.map((high, index) => index === 0
    ? high - lows[index]
    : Math.max(high - lows[index], Math.abs(high - closeValues[index - 1]), Math.abs(lows[index] - closeValues[index - 1])));
  if (ranges.length < period) return [];
  let average = ranges.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  const result = [average];
  for (const value of ranges.slice(period)) {
    average = (average * (period - 1) + value) / period;
    result.push(average);
  }
  return result;
}

export function movingAverageConvergenceDivergence(
  values: readonly number[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9,
): Array<{ macd: number; signal: number; histogram: number }> {
  validatePeriod(fastPeriod);
  validatePeriod(slowPeriod);
  validatePeriod(signalPeriod);
  if (fastPeriod >= slowPeriod) throw new Error('MACD fast period must be smaller than slow period');
  const fast = exponentialMovingAverage(values, fastPeriod);
  const slow = exponentialMovingAverage(values, slowPeriod);
  if (!slow.length) return [];
  const macd = values.slice(slowPeriod - 1).map((_, index) => (
    fast[index + slowPeriod - fastPeriod] - slow[index]
  ));
  const signal = exponentialMovingAverage(macd, signalPeriod);
  if (!signal.length) return [];
  return signal.map((signalValue, index) => {
    const macdValue = macd[index + signalPeriod - 1];
    return { macd: macdValue, signal: signalValue, histogram: macdValue - signalValue };
  });
}

export function anchoredVolumeWeightedAveragePrice(
  bars: readonly MarketBar[],
  anchorTime?: string | null,
): number[] {
  const anchorIndex = anchorTime
    ? bars.findIndex((bar) => Date.parse(bar.start_time) >= Date.parse(anchorTime))
    : 0;
  if (anchorIndex < 0) return [];
  let cumulativePriceVolume = 0;
  let cumulativeVolume = 0;
  const result: number[] = [];
  for (const bar of bars.slice(anchorIndex)) {
    const volume = Number(bar.volume);
    const typical = (Number(bar.high) + Number(bar.low) + Number(bar.close)) / 3;
    cumulativePriceVolume += typical * volume;
    cumulativeVolume += volume;
    result.push(cumulativeVolume === 0 ? typical : cumulativePriceVolume / cumulativeVolume);
  }
  return result;
}

function points(bars: readonly MarketBar[], startIndex: number, values: readonly number[]): IndicatorPoint[] {
  return values.map((value, index) => ({ time: bars[startIndex + index].start_time, value }));
}

export function indicatorOutputs(
  bars: readonly MarketBar[],
  instance: CoreIndicatorInstance,
): IndicatorOutput[] {
  const values = closes(bars);
  if (instance.id === 'sma' || instance.id === 'ema' || instance.id === 'rsi') {
    const outputs = instance.id === 'sma'
      ? simpleMovingAverage(values, instance.period)
      : instance.id === 'ema'
        ? exponentialMovingAverage(values, instance.period)
        : relativeStrengthIndex(values, instance.period);
    const startIndex = instance.id === 'rsi' ? instance.period : instance.period - 1;
    return [{
      key: `${instance.id}:${instance.period}`,
      title: `${instance.id.toUpperCase()} ${instance.period}`,
      pane: instance.id === 'rsi' ? 1 : 0,
      kind: 'line',
      points: points(bars, startIndex, outputs),
    }];
  }
  if (instance.id === 'bollinger') {
    const deviation = instance.standardDeviations ?? 2;
    const bandValues = bollingerBands(values, instance.period, deviation);
    const start = instance.period - 1;
    return [
      { key: `bollinger:${instance.period}:upper`, title: 'BB Upper', pane: 0, kind: 'line', points: points(bars, start, bandValues.map((item) => item.upper)) },
      { key: `bollinger:${instance.period}:middle`, title: 'BB Middle', pane: 0, kind: 'line', points: points(bars, start, bandValues.map((item) => item.middle)) },
      { key: `bollinger:${instance.period}:lower`, title: 'BB Lower', pane: 0, kind: 'line', points: points(bars, start, bandValues.map((item) => item.lower)) },
    ];
  }
  if (instance.id === 'atr') {
    const atrValues = averageTrueRange(
      bars.map((bar) => Number(bar.high)),
      bars.map((bar) => Number(bar.low)),
      values,
      instance.period,
    );
    return [{ key: `atr:${instance.period}`, title: `ATR ${instance.period}`, pane: 1, kind: 'line', points: points(bars, instance.period - 1, atrValues) }];
  }
  if (instance.id === 'macd') {
    const fast = instance.fastPeriod ?? 12;
    const slow = instance.slowPeriod ?? 26;
    const signal = instance.signalPeriod ?? 9;
    const macdValues = movingAverageConvergenceDivergence(values, fast, slow, signal);
    const start = slow + signal - 2;
    return [
      { key: `macd:${fast}:${slow}:line`, title: 'MACD', pane: 1, kind: 'line', points: points(bars, start, macdValues.map((item) => item.macd)) },
      { key: `macd:${fast}:${slow}:signal`, title: 'Signal', pane: 1, kind: 'line', points: points(bars, start, macdValues.map((item) => item.signal)) },
      { key: `macd:${fast}:${slow}:histogram`, title: 'Histogram', pane: 1, kind: 'histogram', points: points(bars, start, macdValues.map((item) => item.histogram)) },
    ];
  }
  const anchorIndex = instance.anchorTime
    ? bars.findIndex((bar) => Date.parse(bar.start_time) >= Date.parse(instance.anchorTime as string))
    : 0;
  const vwapValues = anchoredVolumeWeightedAveragePrice(bars, instance.anchorTime);
  return [{ key: `vwap:${instance.anchorTime ?? 'dataset'}`, title: 'Anchored VWAP', pane: 0, kind: 'line', points: points(bars, Math.max(anchorIndex, 0), vwapValues) }];
}

export function indicatorPoints(
  bars: readonly MarketBar[],
  instance: CoreIndicatorInstance,
): IndicatorPoint[] {
  return indicatorOutputs(bars, instance)[0]?.points ?? [];
}
