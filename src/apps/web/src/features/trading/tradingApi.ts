import type {
  BarsResponse,
  CanonicalInstrument,
  ProviderDescriptor,
  TradingAlert,
  TradingAlertCreateInput,
  TradingAlertTrigger,
  TradingAlertUpdateInput,
  TradingDocument,
  TradingStreamMessage,
} from './tradingTypes';

export type TradingDocumentKind = 'workspaces' | 'watchlists' | 'drawings' | 'indicator-presets';

export type TradingCurrencyRate = {
  base_currency: string;
  quote_currency: string;
  rate: number;
  provider: string;
  received_at: string;
  freshness_mode: string;
};

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

function arrayField<T>(payload: unknown, field: string): T[] {
  if (!payload || typeof payload !== 'object') return [];
  const value = (payload as Record<string, unknown>)[field];
  return Array.isArray(value) ? value as T[] : [];
}

export function tradingStreamUrl(instrumentId: string, interval: string, bindingId?: string | null): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({ instrument_id: instrumentId, interval });
  if (bindingId) query.set('binding_id', bindingId);
  return `${protocol}//${window.location.host}/api/trading/stream?${query.toString()}`;
}

export function subscribeTradingStream(
  instrumentId: string,
  interval: string,
  onMessage: (message: TradingStreamMessage) => void,
  onStatus?: (status: 'connecting' | 'live' | 'closed' | 'error') => void,
  bindingId?: string | null,
): () => void {
  onStatus?.('connecting');
  const socket = new WebSocket(tradingStreamUrl(instrumentId, interval, bindingId));
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

function marketQuery(
  instrumentId: string,
  bindingId?: string | null,
  extra?: Record<string, string>,
): string {
  const query = new URLSearchParams({ instrument_id: instrumentId, ...(extra ?? {}) });
  if (bindingId) query.set('binding_id', bindingId);
  return query.toString();
}

export const tradingApi = {
  providers: async () => {
    const payload = await requestJson<unknown>('/api/trading/providers/status');
    return arrayField<ProviderDescriptor>(payload, 'providers');
  },
  instruments: async (query = '') => {
    const payload = await requestJson<unknown>(
      `/api/trading/instruments/search?query=${encodeURIComponent(query)}`,
    );
    return arrayField<CanonicalInstrument>(payload, 'instruments');
  },
  bars: (instrumentId: string, interval: string, limit = 1_000, bindingId?: string | null) =>
    requestJson<BarsResponse>(
      `/api/trading/bars?${marketQuery(instrumentId, bindingId, { interval, limit: String(limit) })}`,
    ),
  quote: (instrumentId: string, bindingId?: string | null) =>
    requestJson<Record<string, string>>(
      `/api/trading/quotes?${marketQuery(instrumentId, bindingId)}`,
    ),
  currencyRate: (baseCurrency: string, quoteCurrency: string) => {
    const query = new URLSearchParams({ base_currency: baseCurrency, quote_currency: quoteCurrency });
    return requestJson<TradingCurrencyRate>(`/api/trading/currency-rates?${query.toString()}`);
  },
  diagnostics: () => requestJson<{ ok: boolean; diagnostics: Record<string, unknown> }>('/api/trading/diagnostics'),
  documents: async (kind: TradingDocumentKind) => {
    const payload = await requestJson<unknown>(`/api/trading/${kind}`);
    return arrayField<TradingDocument>(payload, 'records');
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
  alerts: async () => {
    const payload = await requestJson<unknown>('/api/trading/alerts', { cache: 'no-store' });
    return arrayField<TradingAlert>(payload, 'alerts');
  },
  alertTriggers: async () => {
    const payload = await requestJson<unknown>('/api/trading/alerts/triggers', { cache: 'no-store' });
    return arrayField<TradingAlertTrigger>(payload, 'triggers');
  },
  createAlert: (input: TradingAlertCreateInput) =>
    requestJson<TradingAlert>('/api/trading/alerts', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  updateAlert: (alert: TradingAlert, input: TradingAlertUpdateInput) =>
    requestJson<TradingAlert>(`/api/trading/alerts/${encodeURIComponent(alert.alert_id)}`, {
      method: 'PUT',
      headers: { 'If-Match': String(alert.revision) },
      body: JSON.stringify(input),
    }),
  archiveAlert: (alert: TradingAlert) =>
    requestJson<TradingAlert>(`/api/trading/alerts/${encodeURIComponent(alert.alert_id)}`, {
      method: 'DELETE',
      headers: { 'If-Match': String(alert.revision) },
    }),
  evaluateAlerts: async (instrumentId: string, observedPrice: string, observedAt?: string) => {
    const payload = await requestJson<unknown>('/api/trading/alerts/evaluate', {
      method: 'POST',
      body: JSON.stringify({
        instrument_id: instrumentId,
        observed_price: observedPrice,
        ...(observedAt ? { observed_at: observedAt } : {}),
      }),
    });
    return arrayField<TradingAlertTrigger>(payload, 'triggers');
  },
};
