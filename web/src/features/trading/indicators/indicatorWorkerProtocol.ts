import type { MarketBar } from '../tradingTypes';
import type { CoreIndicatorInstance, IndicatorOutput } from './coreIndicators';

export type IndicatorWorkerRequest = {
  requestId: number;
  bars: MarketBar[];
  indicators: CoreIndicatorInstance[];
  /** Bars of each indicator's `compareSymbol`, keyed by that symbol. */
  compareBars?: Record<string, MarketBar[]>;
};

export type IndicatorWorkerResponse =
  | { requestId: number; outputs: IndicatorOutput[] }
  | { requestId: number; error: string };
