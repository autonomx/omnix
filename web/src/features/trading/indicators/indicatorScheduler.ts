import type { MarketBar } from '../tradingTypes';
import {
  indicatorDefaultBackgroundColor,
  indicatorOutputs,
  type CoreIndicatorInstance,
  type IndicatorOutput,
} from './coreIndicators';
import { calculateExternalIndicatorOutputs, isExternalIndicatorId } from './externalIndicatorData';
import {
  calculateTradingViewBuiltInOutputs,
  isTradingViewBuiltInId,
  tradingViewBuiltInUsesCompareSeries,
} from './tradingViewBuiltIns';
import type { IndicatorWorkerRequest, IndicatorWorkerResponse } from './indicatorWorkerProtocol';
import type { TradingSessionSpec } from './tradingSessions';

type PendingRequest = {
  resolve: (outputs: IndicatorOutput[] | null) => void;
  reject: (error: Error) => void;
};

type WorkerFactory = () => Worker;

/**
 * Loads a compare symbol's bars on the chart's interval covering the chart's time range (epoch milliseconds of the first and
 * last bar starts). The chart passes a loader that shares its comparison-series query cache.
 */
export type CompareBarsLoader = (instrumentId: string, interval: string, range: { from: number; to: number }) => Promise<readonly MarketBar[]>;
type CompareBars = Record<string, MarketBar[]>;
/** What the chart knows beyond its bars: the instrument's session calendar. */
export type IndicatorCalculationContext = { session?: TradingSessionSpec };

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

function calculateOutputs(
  bars: readonly MarketBar[],
  indicator: CoreIndicatorInstance,
  compareBars: CompareBars | undefined,
  context: IndicatorCalculationContext,
): IndicatorOutput[] {
  const id = String(indicator.id);
  const outputs = isTradingViewBuiltInId(id)
    ? calculateTradingViewBuiltInOutputs(bars, { ...indicator, id, session: context.session }, {
      compareBars: indicator.compareSymbol ? compareBars?.[indicator.compareSymbol] : undefined,
    }) as IndicatorOutput[]
    : indicatorOutputs(bars, indicator);
  return styleOutputs(outputs, indicator);
}

function compareSymbols(indicators: readonly CoreIndicatorInstance[]): string[] {
  return [...new Set(indicators.flatMap((indicator) => (
    indicator.compareSymbol && tradingViewBuiltInUsesCompareSeries(String(indicator.id)) ? [indicator.compareSymbol] : []
  )))];
}

export class TradingIndicatorScheduler {
  private worker: Worker | null = null;
  private readonly pending = new Map<number, PendingRequest>();
  private latestRequestId = 0;
  private destroyed = false;

  constructor(
    workerFactory: WorkerFactory | null = typeof Worker === 'undefined' ? null : defaultWorkerFactory,
    private readonly compareBarsLoader: CompareBarsLoader | null = null,
  ) {
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
    context: IndicatorCalculationContext = {},
  ): Promise<IndicatorOutput[] | null> {
    if (this.destroyed) return Promise.resolve(null);
    const requestId = ++this.latestRequestId;
    const clonedBars = bars.map((bar) => ({ ...bar }));
    const activeIndicators = indicators
      .filter((indicator) => indicator.enabled && indicator.visible !== false)
      .map((indicator) => ({ ...indicator }));
    const externalIndicators = activeIndicators.filter((indicator) => isExternalIndicatorId(String(indicator.id)));
    const localIndicators = activeIndicators.filter((indicator) => !isExternalIndicatorId(String(indicator.id)));
    const symbols = compareSymbols(localIndicators);

    const externalPromise = Promise.all(
      externalIndicators.map((indicator) => calculateExternalIndicatorOutputs(clonedBars, indicator)),
    ).then((groups) => groups.flat());

    if (!this.worker) {
      const localPromise = this.loadCompareBars(symbols, clonedBars).then((compareBars) => (
        localIndicators.flatMap((indicator) => calculateOutputs(clonedBars, indicator, compareBars, context))
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

    // Indicators with a compare symbol wait for its bars; the rest go to the worker at once, as before.
    const localPromise = symbols.length === 0
      ? this.postToWorker(requestId, clonedBars, localIndicators, undefined, context)
      : this.loadCompareBars(symbols, clonedBars).then((compareBars) => (
        requestId === this.latestRequestId && !this.destroyed
          ? this.postToWorker(requestId, clonedBars, localIndicators, compareBars, context)
          : null
      ));

    return Promise.all([localPromise, externalPromise]).then(([local, external]) => {
      if (local === null || requestId !== this.latestRequestId || this.destroyed) return null;
      return [...local, ...external];
    });
  }

  private postToWorker(
    requestId: number,
    bars: MarketBar[],
    indicators: CoreIndicatorInstance[],
    compareBars: CompareBars | undefined,
    context: IndicatorCalculationContext,
  ): Promise<IndicatorOutput[] | null> {
    if (!this.worker) return Promise.resolve(indicators.flatMap((indicator) => calculateOutputs(bars, indicator, compareBars, context)));
    return new Promise<IndicatorOutput[] | null>((resolve, reject) => {
      for (const [pendingId, pending] of this.pending) {
        if (pendingId < requestId) {
          pending.resolve(null);
          this.pending.delete(pendingId);
        }
      }
      this.pending.set(requestId, { resolve, reject });
      const request: IndicatorWorkerRequest = {
        requestId, bars, indicators, ...(compareBars ? { compareBars } : {}), ...(context.session ? { session: context.session } : {}),
      };
      this.worker?.postMessage(request);
    });
  }

  /** The compare symbols' bars on the chart's interval over the chart's time range; a failed load gives no bars. */
  private loadCompareBars(symbols: readonly string[], bars: readonly MarketBar[]): Promise<CompareBars | undefined> {
    const interval = bars[0]?.interval;
    const loader = this.compareBarsLoader;
    const from = Date.parse(bars[0]?.start_time ?? '');
    const to = Date.parse(bars.at(-1)?.start_time ?? '');
    if (symbols.length === 0 || !interval || !loader || !Number.isFinite(from) || !Number.isFinite(to)) return Promise.resolve(undefined);
    return Promise.all(symbols.map((symbol) => loader(symbol, interval, { from, to })
      .then((loaded) => loaded.map((bar) => ({ ...bar })))
      .catch(() => [] as MarketBar[])))
      .then((loaded) => Object.fromEntries(symbols.map((symbol, index) => [symbol, loaded[index]])));
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
