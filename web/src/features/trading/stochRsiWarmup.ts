import type { StochRsi5mConfig } from './tradingStrategyTypes';

const REGULAR_OPEN_MINUTES = 9 * 60 + 30;
const EMA_PERIOD = 5;

type StochRsiPeriods = Pick<StochRsi5mConfig, 'rsi_period' | 'stochastic_period' | 'k_smoothing_period' | 'd_smoothing_period'>;

/** Finished five-minute bars the evaluator needs before the first %K/%D value. */
export function stochRsiWarmupBars(config: StochRsiPeriods): number {
  const stochRsi = config.rsi_period + config.stochastic_period + config.k_smoothing_period + config.d_smoothing_period - 2;
  return Math.max(stochRsi, EMA_PERIOD);
}

/**
 * Earliest ET time ("HH:MM") a setup can arm. The evaluator reads only the
 * current regular session, so it warms up from the open every day
 * (mirrors stoch_rsi_first_signal_et on the server).
 */
export function stochRsiFirstSignalEt(config: StochRsiPeriods): string {
  const minutes = REGULAR_OPEN_MINUTES + 5 * stochRsiWarmupBars(config);
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}
