import type { MarketResearchRequest, MarketResearchResult } from './researchTypes';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading research failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingResearchApi = {
  generate: (request: MarketResearchRequest) =>
    requestJson<MarketResearchResult>('/api/trading/research', {
      method: 'POST',
      body: JSON.stringify(request),
    }),
};
