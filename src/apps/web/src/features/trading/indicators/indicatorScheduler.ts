import type { MarketBar } from '../tradingTypes';
import {
  indicatorDefaultBackgroundColor,
  indicatorOutputs,
  type CoreIndicatorInstance,
  type IndicatorOutput,
} from './coreIndicators';
import { calculateExternalIndicatorOutputs, isExternalIndicatorId } from './externalIndicatorData';
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

function styleOutputs(outputs: IndicatorOutput[], indicator: CoreIndicatorInstance): IndicatorOutput[] {
  const id = String(indicator.id);
  if (!isTradingViewBuiltInId(id)) return outputs;
  return outputs
    .map((output) => ({
      ...output,
      visible: indicator.style?.plots?.[output.key] !== false,
      color: indicator.style?.colors?.[output.key] ?? output.color,
      lineStyle: indicator.style?.lineStyles?.[output.key] ?? output.lineStyle,
      lineWidth: indicator.style?.lineWidth ?? output.lineWidth,
      backgroundVisible: indicator.style?.backgroundVisible !== false,
      backgroundColor: indicator.style?.backgroundColor ?? output.backgroundColor ?? indicatorDefaultBackgroundColor(indicator.id),
      precision: indicator.style?.precision ?? output.precision,
      labelsOnPriceScale: indicator.style?.labelsOnPriceScale ?? output.labelsOnPriceScale ?? false,
      valuesInStatusLine: indicator.style?.valuesInStatusLine ?? output.valuesInStatusLine,
      inputsInStatusLine: indicator.style?.inputsInStatusLine ?? output.inputsInStatusLine,
    }))
    .filter((output) => output.visible !== false);
}

function calculateOutputs(bars: readonly MarketBar[], indicator: CoreIndicatorInstance): IndicatorOutput[] {
  const id = String(indicator.id);
  const outputs = isTradingViewBuiltInId(id)
    ? calculateTradingViewBuiltInOutputs(bars, { ...indicator, id }) as IndicatorOutput[]
    : indicatorOutputs(bars, indicator);
  return styleOutputs(outputs, indicator);
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
    const activeIndicators = indicators
      .filter((indicator) => indicator.enabled && indicator.visible !== false)
      .map((indicator) => ({ ...indicator }));
    const externalIndicators = activeIndicators.filter((indicator) => isExternalIndicatorId(String(indicator.id)));
    const localIndicators = activeIndicators.filter((indicator) => !isExternalIndicatorId(String(indicator.id)));

    const externalPromise = Promise.all(
      externalIndicators.map((indicator) => calculateExternalIndicatorOutputs(clonedBars, indicator)),
    ).then((groups) => groups.flat());

    if (!this.worker) {
      const localPromise = Promise.resolve().then(() => (
        localIndicators.flatMap((indicator) => calculateOutputs(clonedBars, indicator))
      ));
      return Promise.all([localPromise, externalPromise]).then(([local, external]) => (
        requestId === this.latestRequestId && !this.destroyed ? [...local, ...external] : null
      ));
    }

    if (localIndicators.length === 0) {
      return externalPromise.then((external) => (
        requestId === this.latestRequestId && !this.destroyed ? external : null
      ));
    }

    const localPromise = new Promise<IndicatorOutput[] | null>((resolve, reject) => {
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
        indicators: localIndicators,
      };
      this.worker?.postMessage(request);
    });

    return Promise.all([localPromise, externalPromise]).then(([local, external]) => {
      if (local === null || requestId !== this.latestRequestId || this.destroyed) return null;
      return [...local, ...external];
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
