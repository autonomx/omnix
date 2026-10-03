import type { components } from '../../api/generated/types';
export type TradingHealthState = 'healthy' | 'degraded' | 'blocked' | 'unknown';

export type StrategyRuntimeMonitorStatus = components['schemas']['StrategyRuntimeMonitorStatus'];

export type SolanaAIStrategyRecord = components['schemas']['SolanaAIStrategyRecord'];

export type SolanaAIDecisionEvent = {
  strategy_id: string;
  event_id: string;
  instrument_id: string;
  event_type: string;
  state: string;
  observed_at: string;
  payload: Record<string, unknown>;
};

export type TradingStrategyOperationsStatus = {
  observed_at: string;
  paper_monitor: StrategyRuntimeMonitorStatus;
  strategy_monitor: StrategyRuntimeMonitorStatus;
  deep_recovery_shadow_monitor: StrategyRuntimeMonitorStatus;
  prospective_economic_monitor: StrategyRuntimeMonitorStatus;
  solana_ai_monitor: StrategyRuntimeMonitorStatus;
  universe_archive_monitor: StrategyRuntimeMonitorStatus;
  v2_qualification_monitor: StrategyRuntimeMonitorStatus;
  alpaca_status_monitor: StrategyRuntimeMonitorStatus;
  execution_authority: false;
};

export type AccountRiskHealth = components['schemas']['AccountRiskHealth'];

export type ExecutionHealth = components['schemas']['ExecutionHealth'];

export type TradingOperationalHealth = components['schemas']['TradingOperationalHealth'];

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading operations request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingStrategyOperationsApi = {
  status: () => requestJson<TradingStrategyOperationsStatus>('/api/trading/strategy-operations/status'),
  solanaStrategy: () => requestJson<SolanaAIStrategyRecord>('/api/trading/solana-ai/strategy'),
  solanaDecisions: (limit = 20) => requestJson<SolanaAIDecisionEvent[]>(`/api/trading/solana-ai/decisions?limit=${encodeURIComponent(String(limit))}`),
  startSolana: () => requestJson('/api/trading/solana-ai/start', { method: 'POST' }),
  stopSolana: () => requestJson('/api/trading/solana-ai/stop', { method: 'POST' }),
  health: (
    accountId: string,
    options: { instrumentId?: string | null; bindingId?: string | null } = {},
  ) => {
    const params = new URLSearchParams({ account_id: accountId });
    if (options.instrumentId) params.set('instrument_id', options.instrumentId);
    if (options.bindingId) params.set('binding_id', options.bindingId);
    return requestJson<TradingOperationalHealth>(`/api/trading/strategy-operations/health?${params.toString()}`);
  },
};
