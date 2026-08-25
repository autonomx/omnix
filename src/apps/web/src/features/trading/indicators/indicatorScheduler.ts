import type { MarketBar } from '../tradingTypes';
import { indicatorOutputs, type CoreIndicatorInstance, type IndicatorOutput } from './coreIndicators';
import { calculateTradingViewBuiltInOutputs, isTradingViewBuiltInId } from './tradingViewBuiltIns';
import type { IndicatorWorkerRequest, IndicatorWorkerResponse } from './indicatorWorkerProtocol';

type PendingRequest = {
  resolve: (outputs: IndicatorOutput[] | null) => void;
  reject: (error: Error) => void;
};

type WorkerFactory = () => Worker;

function defaultWorkerFactory(): Worker {
  return new Worker(new URL('./indicator.worker.ts', import.meta.url), { type: 'module' });
}

function calculateOutputs(bars: readonly MarketBar[], indicator: CoreIndicatorInstance): IndicatorOutput[] {
  if (isTradingViewBuiltInId(indicator.id)) {
    return calculateTradingViewBuiltInOutputs(bars, indicator) as IndicatorOutput[];
  }
  return indicatorOutputs(bars, indicator);
}

export class TradingIndicatorScheduler {
  private worker: Worker | null = null;
  private readonly pending = new Map<number, PendingRequest>();
  private latestRequestId = 0;
  private destroyed = false;

  constructor(workerFactory: WorkerFactory | null = typeof Worker === 'undefined' ? null : defaultWorkerFactory) {
    if (!workerFactory) return;
    try {
      this.worker = workerFactory();
      this.worker.addEventListener('message', this.onMessage);
      this.worker.addEventListener('error', this.onWorkerError);
    } catch {
      this.worker = null;
    }
  }

  calculate(
    bars: readonly MarketBar[],
    indicators: readonly CoreIndicatorInstance[],
  ): Promise<IndicatorOutput[] | null> {
    if (this.destroyed) return Promise.resolve(null);
    const requestId = ++this.latestRequestId;
    const clonedBars = bars.map((bar) => ({ ...bar }));
    const clonedIndicators = indicators.map((indicator) => ({ ...indicator }));

    if (!this.worker) {
      return Promise.resolve().then(() => {
        const outputs = clonedIndicators
          .filter((indicator) => indicator.enabled && indicator.visible !== false)
          .flatMap((indicator) => calculateOutputs(clonedBars, indicator));
        return requestId === this.latestRequestId && !this.destroyed ? outputs : null;
      });
    }

    return new Promise<IndicatorOutput[] | null>((resolve, reject) => {
      for (const [pendingId, pending] of this.pending) {
        if (pendingId < requestId) {
          pending.resolve(null);
          this.pending.delete(pendingId);
        }
      }
      this.pending.set(requestId, { resolve, reject });
      const request: IndicatorWorkerRequest = {
        requestId,
        bars: clonedBars,
        indicators: clonedIndicators,
      };
      this.worker?.postMessage(request);
    });
  }

  destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    this.worker?.removeEventListener('message', this.onMessage);
    this.worker?.removeEventListener('error', this.onWorkerError);
    this.worker?.terminate();
    this.worker = null;
    for (const pending of this.pending.values()) pending.resolve(null);
    this.pending.clear();
  }

  private readonly onMessage = (event: MessageEvent<IndicatorWorkerResponse>): void => {
    const response = event.data;
    const pending = this.pending.get(response.requestId);
    if (!pending) return;
    this.pending.delete(response.requestId);
    if ('error' in response) {
      pending.reject(new Error(response.error));
      return;
    }
    pending.resolve(response.requestId === this.latestRequestId ? response.outputs : null);
  };

  private readonly onWorkerError = (event: ErrorEvent): void => {
    const error = new Error(event.message || 'Trading indicator worker failed');
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
    this.worker?.terminate();
    this.worker = null;
  };
}
