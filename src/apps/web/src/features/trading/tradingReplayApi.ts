import type { BacktestRunResult, FrozenDatasetSnapshot } from './replayTypes';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading replay request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

function arrayField<T>(payload: unknown, field: string): T[] {
  if (!payload || typeof payload !== 'object') return [];
  const value = (payload as Record<string, unknown>)[field];
  return Array.isArray(value) ? value as T[] : [];
}

export const tradingReplayApi = {
  datasets: async () => {
    const payload = await requestJson<unknown>('/api/trading/replay/datasets');
    return arrayField<FrozenDatasetSnapshot>(payload, 'datasets');
  },
  freeze: (input: {
    dataset_id: string;
    instrument_id: string;
    binding_id?: string | null;
    interval: string;
    limit: number;
    gap_policy: 'fail' | 'skip';
  }) => requestJson<FrozenDatasetSnapshot>('/api/trading/replay/datasets', {
    method: 'POST',
    body: JSON.stringify(input),
  }),
  backtests: async () => {
    const payload = await requestJson<unknown>('/api/trading/replay/backtests');
    return arrayField<Record<string, unknown>>(payload, 'runs');
  },
  runBacktest: (datasetId: string, input: {
    fast_period: number;
    slow_period: number;
    initial_cash: string;
    commission_bps: string;
    slippage_bps: string;
  }) => requestJson<BacktestRunResult>('/api/trading/replay/backtests', {
    method: 'POST',
    body: JSON.stringify({
      dataset_id: datasetId,
      request: {
        strategy: {
          strategy_id: 'sma_cross',
          fast_period: input.fast_period,
          slow_period: input.slow_period,
        },
        execution_policy: {
          fill_timing: 'next_bar_open',
          commission_bps: input.commission_bps,
          slippage_bps: input.slippage_bps,
          position_size_fraction: '1',
          allow_short: false,
          use_finalized_bars_only: true,
        },
        initial_cash: input.initial_cash,
        formula_version: 'omnix-indicators-v2',
      },
    }),
  }),
  backtest: (runId: string) => requestJson<BacktestRunResult>(
    `/api/trading/replay/backtests/${encodeURIComponent(runId)}`,
  ),
};
