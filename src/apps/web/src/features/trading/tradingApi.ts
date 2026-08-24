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
  MarketBar,
} from './tradingTypes';
import { decodeTradingFormula, evaluateTradingFormula, parseTradingFormula } from './tradingFormula';

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

function formulaInstrument(instrumentId: string, expression: string, source: CanonicalInstrument): CanonicalInstrument {
  return {
    ...source,
    instrument_id: instrumentId,
    display_symbol: expression,
    venue_symbol: expression,
    venue: 'DERIVED',
    instrument_type: 'index',
    base_currency: null,
    quote_currency: null,
    minimum_tick: '0.00000001',
    price_scale: 100,
  };
}

function formulaBarNumber(bar: MarketBar | undefined, field: 'open' | 'high' | 'low' | 'close' | 'volume'): number | null {
  const value = Number(bar?.[field]);
  return Number.isFinite(value) ? value : null;
}

function normalizedFormulaSymbol(value: string): string {
  return value.toUpperCase().replace(/[-:_/]/g, '');
}

function isCanonicalFormulaOperand(value: string): boolean {
  return /^(crypto|equity):/i.test(value);
}

async function resolveFormulaOperand(symbol: string, operandId: string): Promise<string> {
  if (isCanonicalFormulaOperand(operandId)) return operandId;

  const candidates = arrayField<CanonicalInstrument>(
    await requestJson<unknown>(`/api/trading/instruments/search?query=${encodeURIComponent(operandId || symbol)}`),
    'instruments',
  );
  const normalized = normalizedFormulaSymbol(operandId || symbol);
  const match = candidates.find((candidate) => [
    candidate.display_symbol,
    candidate.venue_symbol,
    candidate.instrument_id,
  ].some((value) => normalizedFormulaSymbol(value) === normalized));
  if (!match) throw new Error(`Arithmetic chart symbol could not be resolved: ${symbol}`);
  return match.instrument_id;
}

async function formulaBars(
  instrumentId: string,
  interval: string,
  limit: number,
): Promise<BarsResponse> {
  const payload = decodeTradingFormula(instrumentId);
  if (!payload) throw new Error('Invalid arithmetic chart formula.');
  const formula = parseTradingFormula(payload.expression, { symbolHints: Object.keys(payload.operands) });
  if (!formula) throw new Error('Invalid arithmetic chart formula.');

  const operandIds = await Promise.all(formula.symbols.map((symbol) => resolveFormulaOperand(
    symbol,
    payload.operands[symbol] ?? symbol,
  )));
  const responses = await Promise.all(operandIds.map((operandId) => requestJson<BarsResponse>(
    `/api/trading/bars?${marketQuery(operandId, undefined, { interval, limit: String(limit) })}`,
  )));
  const source = responses[0];
  if (!source) throw new Error('Arithmetic chart formula has no market data.');

  const operandBars = new Map(formula.symbols.map((symbol, index) => [symbol, responses[index]?.bars ?? []]));
  const cursors = new Map(formula.symbols.map((symbol) => [symbol, 0]));
  const valueAt = (symbol: string, time: number, field: 'open' | 'high' | 'low' | 'close'): number | null => {
    const bars = operandBars.get(symbol) ?? [];
    if (bars.length === 0) return null;
    let cursor = cursors.get(symbol) ?? 0;
    while (cursor + 1 < bars.length && Date.parse(bars[cursor + 1].start_time) <= time) cursor += 1;
    cursors.set(symbol, cursor);
    if (Date.parse(bars[cursor]?.start_time ?? '') > time) return null;
    return formulaBarNumber(bars[cursor], field);
  };

  const bars = source.bars.flatMap((sourceBar) => {
    const time = Date.parse(sourceBar.start_time);
    if (!Number.isFinite(time)) return [];
    const values = (field: 'open' | 'high' | 'low' | 'close') => evaluateTradingFormula(
      formula.root,
      (symbol) => valueAt(symbol, time, field),
    );
    const open = values('open');
    const high = values('high');
    const low = values('low');
    const close = values('close');
    if ([open, high, low, close].some((value) => value === null)) return [];
    const normalizedValues = [open as number, high as number, low as number, close as number];
    const volume = formula.symbols.reduce((sum, symbol) => sum + (formulaBarNumber(
      operandBars.get(symbol)?.[cursors.get(symbol) ?? 0],
      'volume',
    ) ?? 0), 0);
    return [{
      ...sourceBar,
      instrument_id: instrumentId,
      open: String(normalizedValues[0]),
      high: String(Math.max(...normalizedValues)),
      low: String(Math.min(...normalizedValues)),
      close: String(normalizedValues[3]),
      volume: String(Math.max(0, volume)),
      provider: 'DERIVED',
      provider_event_id: null,
      provider_sequence: null,
      received_at: sourceBar.received_at ?? source.provenance.received_at,
    }];
  });

  const binding = {
    ...source.binding,
    binding_id: `formula:${source.binding.binding_id}`,
    instrument_id: instrumentId,
    provider: 'DERIVED',
    provider_symbol: payload.expression,
    realtime_scope: 'none',
  };
  return {
    ...source,
    bars,
    binding,
    instrument: formulaInstrument(instrumentId, payload.expression, source.instrument),
    provenance: { ...source.provenance, instrument_id: instrumentId },
  };
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
  bars: (instrumentId: string, interval: string, limit = 1_000, bindingId?: string | null) => {
    if (decodeTradingFormula(instrumentId)) return formulaBars(instrumentId, interval, limit);
    return requestJson<BarsResponse>(
      `/api/trading/bars?${marketQuery(instrumentId, bindingId, { interval, limit: String(limit) })}`,
    );
  },
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
