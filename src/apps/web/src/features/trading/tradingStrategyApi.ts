import type {
  GapperUniverse,
  GapperUniverseFreezeInput,
  StrategyEvent,
  StrategyProtection,
  TradingStrategyConfig,
} from './tradingStrategyTypes';

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
    throw new Error(`Trading strategy request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingStrategyApi = {
  list: async () => {
    const payload = await requestJson<{ strategies?: TradingStrategyConfig[] }>('/api/trading/strategies');
    return Array.isArray(payload.strategies) ? payload.strategies : [];
  },
  get: (strategyId: string) =>
    requestJson<TradingStrategyConfig>(`/api/trading/strategies/${encodeURIComponent(strategyId)}`),
  create: (config: TradingStrategyConfig) =>
    requestJson<TradingStrategyConfig>('/api/trading/strategies', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  update: (config: TradingStrategyConfig) =>
    requestJson<TradingStrategyConfig>(`/api/trading/strategies/${encodeURIComponent(config.strategy_id)}`, {
      method: 'PUT',
      headers: { 'If-Match': String(config.revision) },
      body: JSON.stringify(config),
    }),
  events: async (strategyId: string, limit = 100) => {
    const payload = await requestJson<{ events?: StrategyEvent[] }>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/events?limit=${limit}`,
    );
    return Array.isArray(payload.events) ? payload.events : [];
  },
  protections: async (strategyId: string) => {
    const payload = await requestJson<{ protections?: StrategyProtection[] }>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/protections?active_only=true`,
    );
    return Array.isArray(payload.protections) ? payload.protections : [];
  },
  freezeUniverse: (input: GapperUniverseFreezeInput) =>
    requestJson<GapperUniverse>('/api/trading/strategies/universes/freeze', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  universe: (universeId: string) =>
    requestJson<GapperUniverse>(`/api/trading/strategies/universes/${encodeURIComponent(universeId)}`),
};
