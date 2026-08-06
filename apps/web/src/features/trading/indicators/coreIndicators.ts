import type { MarketBar } from '../tradingTypes';

export const CORE_INDICATOR_FORMULA_VERSION = 'omnix-indicators-v1';

export type IndicatorPoint = { time: string; value: number };
export type CoreIndicatorId = 'sma' | 'ema' | 'rsi';
export type CoreIndicatorInstance = { id: CoreIndicatorId; period: number; enabled: boolean };

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

export function indicatorPoints(
  bars: readonly MarketBar[],
  instance: CoreIndicatorInstance,
): IndicatorPoint[] {
  const values = closes(bars);
  const outputs = instance.id === 'sma'
    ? simpleMovingAverage(values, instance.period)
    : instance.id === 'ema'
      ? exponentialMovingAverage(values, instance.period)
      : relativeStrengthIndex(values, instance.period);
  const startIndex = instance.id === 'rsi' ? instance.period : instance.period - 1;
  return outputs.map((value, index) => ({ time: bars[startIndex + index].start_time, value }));
}
