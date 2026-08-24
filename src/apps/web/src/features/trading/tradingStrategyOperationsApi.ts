export type TradingHealthState = 'healthy' | 'degraded' | 'blocked' | 'unknown';

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
  paper_monitor: StrategyRuntimeMonitorStatus;
  strategy_monitor: StrategyRuntimeMonitorStatus;
  deep_recovery_shadow_monitor: StrategyRuntimeMonitorStatus;
  prospective_economic_monitor: StrategyRuntimeMonitorStatus;
  universe_archive_monitor: StrategyRuntimeMonitorStatus;
  v2_qualification_monitor: StrategyRuntimeMonitorStatus;
  alpaca_status_monitor: StrategyRuntimeMonitorStatus;
  execution_authority: false;
};

export type AccountRiskHealth = {
  state: TradingHealthState;
  reason_codes: string[];
  account_id: string;
  policy_source: 'active_strategy' | 'paper_default';
  equity: string;
  buying_power: string;
  open_risk_dollars: string;
  open_risk_pct: string;
  max_open_risk_pct: string;
  daily_realized_pnl: string;
  daily_loss_limit_dollars: string;
  daily_loss_remaining: string;
  max_daily_loss_pct: string;
  unprotected_exposure_count: number;
  position_count: number;
  open_order_count: number;
  active_protection_count: number;
};

export type ExecutionHealth = {
  state: TradingHealthState;
  reason_codes: string[];
  instrument_id?: string | null;
  requested_binding_id?: string | null;
  resolved_binding_id?: string | null;
  provider?: string | null;
  policy_version?: string | null;
  execution_eligible: boolean;
  source_time?: string | null;
  observation_age_ms?: string | null;
  spread_bps?: string | null;
  freshness_mode?: string | null;
  session?: string | null;
  halted?: boolean | null;
};

export type TradingOperationalHealth = {
  observed_at: string;
  state: TradingHealthState;
  reason_codes: string[];
  risk: AccountRiskHealth;
  execution: ExecutionHealth;
  paper_only: true;
  live_broker_enabled: false;
  ai_order_placement_enabled: false;
};

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { 'content-type': 'application/json' } });
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
