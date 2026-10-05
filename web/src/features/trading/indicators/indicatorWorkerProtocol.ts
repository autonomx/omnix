import type { MarketBar } from '../tradingTypes';
import type { CoreIndicatorInstance, IndicatorOutput } from './coreIndicators';

export type IndicatorWorkerRequest = {
  requestId: number;
  bars: MarketBar[];
  indicators: CoreIndicatorInstance[];
};

export type IndicatorWorkerResponse =
  | { requestId: number; outputs: IndicatorOutput[] }
  | { requestId: number; error: string };
