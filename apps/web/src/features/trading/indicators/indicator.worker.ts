/// <reference lib="webworker" />

import { indicatorOutputs } from './coreIndicators';
import type { IndicatorWorkerRequest, IndicatorWorkerResponse } from './indicatorWorkerProtocol';

const workerScope: DedicatedWorkerGlobalScope = self as unknown as DedicatedWorkerGlobalScope;

workerScope.addEventListener('message', (event: MessageEvent<IndicatorWorkerRequest>) => {
  const request = event.data;
  try {
    const outputs = request.indicators
      .filter((indicator) => indicator.enabled && indicator.visible !== false)
      .flatMap((indicator) => indicatorOutputs(request.bars, indicator));
    const response: IndicatorWorkerResponse = { requestId: request.requestId, outputs };
    workerScope.postMessage(response);
  } catch (error) {
    const response: IndicatorWorkerResponse = {
      requestId: request.requestId,
      error: error instanceof Error ? error.message : String(error),
    };
    workerScope.postMessage(response);
  }
});

export {};
