import type {
  TradingScannerDefinition,
  TradingScannerResult,
  TradingScannerRun,
} from './scannerTypes';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading scanner request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingScannerApi = {
  definitions: async () => {
    const payload = await requestJson<{ scanners: TradingScannerDefinition[] }>('/api/trading/scanners');
    return payload.scanners;
  },
  create: (definition: TradingScannerDefinition) =>
    requestJson<TradingScannerDefinition>('/api/trading/scanners', {
      method: 'POST',
      body: JSON.stringify(definition),
    }),
  update: (definition: TradingScannerDefinition) =>
    requestJson<TradingScannerDefinition>(`/api/trading/scanners/${encodeURIComponent(definition.scanner_id)}`, {
      method: 'PUT',
      headers: { 'If-Match': String(definition.revision) },
      body: JSON.stringify(definition),
    }),
  start: (scannerId: string) =>
    requestJson<TradingScannerRun>(`/api/trading/scanners/${encodeURIComponent(scannerId)}/runs`, { method: 'POST' }),
  cancel: (runId: string) =>
    requestJson<{ ok: boolean; run_id: string; status: string }>(`/api/trading/scanners/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' }),
  runs: async (scannerId?: string) => {
    const query = scannerId ? `?scanner_id=${encodeURIComponent(scannerId)}` : '';
    const payload = await requestJson<{ runs: TradingScannerRun[] }>(`/api/trading/scanners/runs${query}`);
    return payload.runs;
  },
  results: async (runId: string) => {
    const payload = await requestJson<{ results: TradingScannerResult[] }>(
      `/api/trading/scanners/runs/${encodeURIComponent(runId)}/results`,
    );
    return payload.results;
  },
};
