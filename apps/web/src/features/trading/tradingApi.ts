import type { CanonicalInstrument, ProviderDescriptor, TradingDocument } from './tradingTypes';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingApi = {
  providers: async () => {
    const payload = await requestJson<{ providers: ProviderDescriptor[] }>('/api/trading/providers/status');
    return payload.providers;
  },
  instruments: async (query = '') => {
    const payload = await requestJson<{ instruments: CanonicalInstrument[] }>(
      `/api/trading/instruments/search?query=${encodeURIComponent(query)}`,
    );
    return payload.instruments;
  },
  documents: async (kind: 'workspaces' | 'watchlists' | 'drawings' | 'indicator-presets') => {
    const payload = await requestJson<{ records: TradingDocument[] }>(`/api/trading/${kind}`);
    return payload.records;
  },
  createDocument: (kind: 'workspaces' | 'watchlists' | 'drawings' | 'indicator-presets', recordId: string, payload: Record<string, unknown>) =>
    requestJson<TradingDocument>(`/api/trading/${kind}`, {
      method: 'POST',
      body: JSON.stringify({ record_id: recordId, payload }),
    }),
  updateDocument: (
    kind: 'workspaces' | 'watchlists' | 'drawings' | 'indicator-presets',
    record: TradingDocument,
    payload: Record<string, unknown>,
  ) =>
    requestJson<TradingDocument>(`/api/trading/${kind}/${encodeURIComponent(record.record_id)}`, {
      method: 'PUT',
      headers: { 'If-Match': String(record.revision) },
      body: JSON.stringify({ record_id: record.record_id, payload }),
    }),
};
