import type { components } from '../../api/generated/types';

export type AnalyticsNumeric = string | number;
export type PaperAnalyticsMode = 'all' | 'shadow' | 'auto_paper';

export type PaperSimulationEpoch = components['schemas']['PaperSimulationEpoch'];

export type PaperEquityPoint = components['schemas']['PaperEquityPoint'];

export type PaperAnalyticsTrade = components['schemas']['PaperAnalyticsTrade'];

export type PaperPerformanceSummary = components['schemas']['PaperPerformanceSummary'];

export type PaperModeComparison = components['schemas']['PaperModeComparison'];

export type PaperDailyR = components['schemas']['PaperDailyR'];

export type PaperDrawdownPoint = components['schemas']['PaperDrawdownPoint'];

export type PaperRollingExpectancyPoint = components['schemas']['PaperRollingExpectancyPoint'];

export type PaperRDistributionBucket = components['schemas']['PaperRDistributionBucket'];

export type PaperMaeMfePoint = components['schemas']['PaperMaeMfePoint'];

export type PaperFunnelStage = components['schemas']['PaperFunnelStage'];

export type PaperExecutionSummary = components['schemas']['PaperExecutionSummary'];

export type PaperFactorBucket = components['schemas']['PaperFactorBucket'];

export type PaperFactorStudy = components['schemas']['PaperFactorStudy'];

export type PaperTradeJournalEvent = components['schemas']['PaperTradeJournalEvent'];

export type PaperTradeJournalEntry = components['schemas']['PaperTradeJournalEntry'];

export type PaperTradeJournalResponse = components['schemas']['PaperTradeJournalResponse'];

export type PaperAnalyticsOverview = components['schemas']['PaperAnalyticsOverview'];

export interface PaperAnalyticsFilters {
  accountId: string;
  strategyId?: string | null;
  epochId?: string | null;
  mode?: PaperAnalyticsMode;
  startDate?: string | null;
  endDate?: string | null;
  rollingWindow?: number;
}

export interface PaperJournalFilters {
  accountId: string;
  strategyId?: string | null;
  epochId?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  limit?: number;
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

function journalQuery(filters: PaperJournalFilters): string {
  const params = new URLSearchParams({ account_id: filters.accountId });
  if (filters.strategyId) params.set('strategy_id', filters.strategyId);
  if (filters.epochId) params.set('epoch_id', filters.epochId);
  if (filters.startDate) params.set('start_date', filters.startDate);
  if (filters.endDate) params.set('end_date', filters.endDate);
  if (filters.limit) params.set('limit', String(filters.limit));
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
  journal: (filters: PaperJournalFilters) =>
    requestJson<PaperTradeJournalResponse>(`/api/trading/paper-analytics/journal?${journalQuery(filters)}`),
};
