import { describe, expect, it } from 'vitest';

import { stochRsiFirstSignalEt, stochRsiWarmupBars } from './stochRsiWarmup';

describe('stochRsiFirstSignalEt', () => {
  it('needs 32 bars for 14/14/3/3, so no signal before 12:10 ET', () => {
    const config = { rsi_period: 14, stochastic_period: 14, k_smoothing_period: 3, d_smoothing_period: 3 };
    expect(stochRsiWarmupBars(config)).toBe(32);
    expect(stochRsiFirstSignalEt(config)).toBe('12:10');
  });

  it('gives 11:20 ET for the 9/9/3/3 fast child', () => {
    expect(stochRsiFirstSignalEt({ rsi_period: 9, stochastic_period: 9, k_smoothing_period: 3, d_smoothing_period: 3 })).toBe('11:20');
  });

  it('never needs fewer bars than the 5-period EMA', () => {
    expect(stochRsiWarmupBars({ rsi_period: 2, stochastic_period: 2, k_smoothing_period: 1, d_smoothing_period: 1 })).toBe(5);
  });
});
