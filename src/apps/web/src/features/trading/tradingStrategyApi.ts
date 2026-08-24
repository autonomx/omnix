import type {
  GapperUniverse,
  GapperUniverseFreezeInput,
  StrategyCatalystCaptureResponse,
  StrategyEvent,
  StrategyProtection,
  StrategyRangeBacktestInput,
  StrategyRangeBacktestResult,
  StrategyResearchReviewResponse,
  TradingStrategyConfig,
  V2ProspectiveQualification,
  YahooGapperDiscoveryInput,
} from './tradingStrategyTypes';

const DEEP_RECOVERY_EVENT_TYPES = new Set(['deep_recovery_state', 'deep_recovery_shadow']);

export type StrategyRuntimeMonitorStatus = {
  configured_enabled: boolean;
  registered: boolean;
  running: boolean;
  interval_seconds: number | null;
  last_run_at: string | null;
  last_error: string | null;
  counters: Record<string, number>;
};

export type TradingStrategyOperationsStatus = {
  observed_at: string;
  strategy_monitor: StrategyRuntimeMonitorStatus;
  deep_recovery_shadow_monitor: StrategyRuntimeMonitorStatus;
  universe_archive_monitor: StrategyRuntimeMonitorStatus;
  v2_qualification_monitor: StrategyRuntimeMonitorStatus;
  alpaca_status_monitor: StrategyRuntimeMonitorStatus;
  execution_authority: false;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading strategy request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

async function strategyEvents(strategyId: string, limit: number): Promise<StrategyEvent[]> {
  const payload = await requestJson<{ events?: StrategyEvent[] }>(
    `/api/trading/strategies/${encodeURIComponent(strategyId)}/events?limit=${limit}`,
  );
  return Array.isArray(payload.events) ? payload.events : [];
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
  delete: (config: TradingStrategyConfig) =>
    requestJson<void>(`/api/trading/strategies/${encodeURIComponent(config.strategy_id)}`, {
      method: 'DELETE',
      headers: { 'If-Match': String(config.revision) },
    }),
  backtestRange: (strategyId: string, input: StrategyRangeBacktestInput) =>
    requestJson<StrategyRangeBacktestResult>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/backtest/range`,
      { method: 'POST', body: JSON.stringify(input) },
    ),
  events: async (strategyId: string, limit = 200) => {
    const rows = await strategyEvents(strategyId, Math.max(limit, 500));
    return rows.filter((event) => !DEEP_RECOVERY_EVENT_TYPES.has(event.event_type)).slice(0, limit);
  },
  deepRecoveryEvents: async (strategyId: string, limit = 200) => {
    const rows = await strategyEvents(strategyId, Math.max(limit, 500));
    return rows.filter((event) => DEEP_RECOVERY_EVENT_TYPES.has(event.event_type)).slice(0, limit);
  },
  protections: async (strategyId: string) => {
    const payload = await requestJson<{ protections?: StrategyProtection[] }>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/protections?active_only=true`,
    );
    return Array.isArray(payload.protections) ? payload.protections : [];
  },
  operationsStatus: () =>
    requestJson<TradingStrategyOperationsStatus>('/api/trading/strategy-operations/status'),
  v2Qualification: (strategyId: string) =>
    requestJson<V2ProspectiveQualification>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/v2/qualification`,
    ),
  reviewV2Qualification: (strategyId: string, reviewNote: string) =>
    requestJson<V2ProspectiveQualification>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/v2/qualification/review`,
      { method: 'POST', body: JSON.stringify({ review_note: reviewNote }) },
    ),
  discoverYahooUniverse: (input: YahooGapperDiscoveryInput) => requestJson<GapperUniverse>(
    '/api/trading/strategies/universes/discover-yahoo',
    { method: 'POST', body: JSON.stringify(input) },
  ),
  freezeUniverse: (input: GapperUniverseFreezeInput) =>
    requestJson<GapperUniverse>('/api/trading/strategies/universes/freeze', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  universe: (universeId: string) =>
    requestJson<GapperUniverse>(`/api/trading/strategies/universes/${encodeURIComponent(universeId)}`),
  captureYahooResearch: (strategyId: string, lookbackHours = 72, maxItemsPerCandidate = 8) =>
    requestJson<StrategyCatalystCaptureResponse>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/research/capture-yahoo`,
      {
        method: 'POST',
        body: JSON.stringify({
          lookback_hours: lookbackHours,
          max_items_per_candidate: maxItemsPerCandidate,
        }),
      },
    ),
  runLlmResearch: (strategyId: string, model?: string) =>
    requestJson<StrategyResearchReviewResponse>(
      `/api/trading/strategies/${encodeURIComponent(strategyId)}/research/llm-review`,
      { method: 'POST', body: JSON.stringify({ model: model?.trim() || null }) },
    ),
};