import type { V2ProspectiveQualification } from './tradingStrategyTypes';

export type AnalyticsNumeric = string | number;
export type PaperAnalyticsMode = 'all' | 'shadow' | 'auto_paper';

export interface PaperSimulationEpoch {
  account_id: string;
  epoch_id: string;
  ordinal: number;
  initial_cash: AnalyticsNumeric;
  started_at: string;
  ended_at?: string | null;
  is_current: boolean;
  end_reason?: string | null;
}

export interface PaperEquityPoint {
  epoch_id: string;
  observed_at: string;
  cash: AnalyticsNumeric;
  equity: AnalyticsNumeric;
  realized_pnl: AnalyticsNumeric;
  unrealized_pnl: AnalyticsNumeric;
  gross_exposure: AnalyticsNumeric;
  risk_at_stop: AnalyticsNumeric;
}

export interface PaperAnalyticsTrade {
  trade_id: string;
  source: 'auto_paper' | 'shadow_replay';
  strategy_id: string;
  strategy_version?: string | null;
  profile_fingerprint?: string | null;
  epoch_id?: string | null;
  universe_id?: string | null;
  instrument_id: string;
  session_date: string;
  entry_time: string;
  exit_time: string;
  exit_reason?: string | null;
  quantity?: AnalyticsNumeric | null;
  realized_pnl?: AnalyticsNumeric | null;
  r_result: AnalyticsNumeric;
  mae_r?: AnalyticsNumeric | null;
  mfe_r?: AnalyticsNumeric | null;
  signal_to_executable_bps?: AnalyticsNumeric | null;
  fill_slippage_bps?: AnalyticsNumeric | null;
  implementation_shortfall_bps?: AnalyticsNumeric | null;
  initial_stop?: AnalyticsNumeric | null;
  initial_target?: AnalyticsNumeric | null;
  setup_features: Record<string, unknown>;
}

export interface PaperPerformanceSummary {
  trade_count: number;
  wins: number;
  losses: number;
  win_rate?: AnalyticsNumeric | null;
  expectancy_r?: AnalyticsNumeric | null;
  total_r: AnalyticsNumeric;
  profit_factor?: AnalyticsNumeric | null;
  average_mae_r?: AnalyticsNumeric | null;
  average_mfe_r?: AnalyticsNumeric | null;
  max_drawdown_r?: AnalyticsNumeric | null;
}

export interface PaperDailyR {
  session_date: string;
  r_result: AnalyticsNumeric;
  trade_count: number;
}

export interface PaperDrawdownPoint {
  observed_at: string;
  drawdown: AnalyticsNumeric;
  unit: 'R' | 'percent';
}

export interface PaperRollingExpectancyPoint {
  observed_at: string;
  sample_size: number;
  expectancy_r: AnalyticsNumeric;
  one_sided_90_lcb_r?: AnalyticsNumeric | null;
}

export interface PaperRDistributionBucket {
  label: string;
  minimum_r?: AnalyticsNumeric | null;
  maximum_r?: AnalyticsNumeric | null;
  count: number;
}

export interface PaperMaeMfePoint {
  trade_id: string;
  instrument_id: string;
  session_date: string;
  r_result: AnalyticsNumeric;
  mae_r: AnalyticsNumeric;
  mfe_r: AnalyticsNumeric;
  risk_dollars?: AnalyticsNumeric | null;
  exit_reason?: string | null;
}

export interface PaperFunnelStage {
  stage: string;
  count: number;
  conversion_from_previous?: AnalyticsNumeric | null;
  dominant_drop_reason?: string | null;
  dominant_drop_count: number;
}

export interface PaperExecutionSummary {
  trade_count: number;
  average_signal_to_executable_bps?: AnalyticsNumeric | null;
  average_fill_slippage_bps?: AnalyticsNumeric | null;
  average_implementation_shortfall_bps?: AnalyticsNumeric | null;
}

export interface PaperFactorBucket {
  label: string;
  count: number;
  expectancy_r: AnalyticsNumeric;
  win_rate: AnalyticsNumeric;
}

export interface PaperFactorStudy {
  factor: string;
  buckets: PaperFactorBucket[];
}

export interface PaperAnalyticsOverview {
  account_id: string;
  strategy_id?: string | null;
  epoch_id?: string | null;
  mode: PaperAnalyticsMode;
  start_date?: string | null;
  end_date?: string | null;
  rolling_window: number;
  epochs: PaperSimulationEpoch[];
  qualification?: V2ProspectiveQualification | null;
  summary: PaperPerformanceSummary;
  equity: PaperEquityPoint[];
  drawdown: PaperDrawdownPoint[];
  daily_r: PaperDailyR[];
  rolling_expectancy: PaperRollingExpectancyPoint[];
  r_distribution: PaperRDistributionBucket[];
  mae_mfe: PaperMaeMfePoint[];
  funnel: PaperFunnelStage[];
  execution: PaperExecutionSummary;
  factors: PaperFactorStudy[];
  recent_trades: PaperAnalyticsTrade[];
  archived_strategy_count: number;
}

export interface PaperAnalyticsFilters {
  accountId: string;
  strategyId?: string | null;
  epochId?: string | null;
  mode?: PaperAnalyticsMode;
  startDate?: string | null;
  endDate?: string | null;
  rollingWindow?: number;
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { accept: 'application/json' } });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Paper analytics request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

function query(filters: PaperAnalyticsFilters): string {
  const params = new URLSearchParams({ account_id: filters.accountId });
  if (filters.strategyId) params.set('strategy_id', filters.strategyId);
  if (filters.epochId) params.set('epoch_id', filters.epochId);
  if (filters.mode) params.set('mode', filters.mode);
  if (filters.startDate) params.set('start_date', filters.startDate);
  if (filters.endDate) params.set('end_date', filters.endDate);
  if (filters.rollingWindow) params.set('rolling_window', String(filters.rollingWindow));
  return params.toString();
}

export const tradingPaperAnalyticsApi = {
  epochs: async (accountId: string) => {
    const payload = await requestJson<{ epochs?: PaperSimulationEpoch[] }>(
      `/api/trading/paper-analytics/epochs?${new URLSearchParams({ account_id: accountId })}`,
    );
    return Array.isArray(payload.epochs) ? payload.epochs : [];
  },
  overview: (filters: PaperAnalyticsFilters) =>
    requestJson<PaperAnalyticsOverview>(`/api/trading/paper-analytics/overview?${query(filters)}`),
};
