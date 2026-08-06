import type {
  BarsResponse,
  CanonicalInstrument,
  ProviderDescriptor,
  TradingDocument,
  TradingStreamMessage,
} from './tradingTypes';

export type TradingDocumentKind = 'workspaces' | 'watchlists' | 'drawings' | 'indicator-presets';

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

export function tradingStreamUrl(instrumentId: string, interval: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ instrument_id: instrumentId, interval });
  return `${protocol}//${window.location.host}/api/trading/stream?${query.toString()}`;
}

export function subscribeTradingStream(
  instrumentId: string,
  interval: string,
  onMessage: (message: TradingStreamMessage) => void,
  onStatus?: (status: 'connecting' | 'live' | 'closed' | 'error') => void,
): () => void {
  onStatus?.('connecting');
  const socket = new WebSocket(tradingStreamUrl(instrumentId, interval));
  socket.addEventListener('open', () => onStatus?.('live'));
  socket.addEventListener('message', (event) => {
    try {
      onMessage(JSON.parse(String(event.data)) as TradingStreamMessage);
    } catch {
      onMessage({ type: 'error', code: 'invalid_stream_message', message: 'Trading stream returned invalid JSON.' });
    }
  });
  socket.addEventListener('error', () => onStatus?.('error'));
  socket.addEventListener('close', () => onStatus?.('closed'));
  return () => socket.close(1000, 'chart disposed');
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
  bars: (instrumentId: string, interval: string, limit = 1_000) => {
    const query = new URLSearchParams({ instrument_id: instrumentId, interval, limit: String(limit) });
    return requestJson<BarsResponse>(`/api/trading/bars?${query.toString()}`);
  },
  quote: (instrumentId: string) => {
    const query = new URLSearchParams({ instrument_id: instrumentId });
    return requestJson<Record<string, string>>(`/api/trading/quotes?${query.toString()}`);
  },
  diagnostics: () => requestJson<{ ok: boolean; diagnostics: Record<string, unknown> }>('/api/trading/diagnostics'),
  documents: async (kind: TradingDocumentKind) => {
    const payload = await requestJson<{ records: TradingDocument[] }>(`/api/trading/${kind}`);
    return payload.records;
  },
  createDocument: (kind: TradingDocumentKind, recordId: string, payload: Record<string, unknown>) =>
    requestJson<TradingDocument>(`/api/trading/${kind}`, {
      method: 'POST',
      body: JSON.stringify({ record_id: recordId, payload }),
    }),
  updateDocument: (kind: TradingDocumentKind, record: TradingDocument, payload: Record<string, unknown>) =>
    requestJson<TradingDocument>(`/api/trading/${kind}/${encodeURIComponent(record.record_id)}`, {
      method: 'PUT',
      headers: { 'If-Match': String(record.revision) },
      body: JSON.stringify({ record_id: record.record_id, payload }),
    }),
  archiveDocument: (kind: TradingDocumentKind, record: TradingDocument) =>
    requestJson<TradingDocument>(`/api/trading/${kind}/${encodeURIComponent(record.record_id)}`, {
      method: 'DELETE',
      headers: { 'If-Match': String(record.revision) },
    }),
};
