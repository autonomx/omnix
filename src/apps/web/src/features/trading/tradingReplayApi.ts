import type { PaperAccountSnapshot, PaperOrder, PaperOrderInput } from './paperTypes';
import type { BacktestRunResult, FrozenDatasetSnapshot } from './replayTypes';
import type { MarketBar } from './tradingTypes';
import { api, unwrapLabelled } from '../../api/http';

const replay = <T>(call: Promise<{ data?: T; error?: unknown; response: Response }>) => unwrapLabelled(call, 'Trading replay');

function replayBar(bar: MarketBar) {
  return {
    instrument_id: bar.instrument_id,
    binding_id: null,
    start_time: bar.start_time,
    end_time: bar.end_time,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    volume: bar.volume,
  };
}

export const tradingReplayApi = {
  datasets: async (): Promise<FrozenDatasetSnapshot[]> =>
    (await replay(api.GET('/api/trading/replay/datasets'))).datasets,
  freeze: (input: {
    dataset_id: string;
    instrument_id: string;
    binding_id?: string | null;
    interval: string;
    limit: number;
    gap_policy: 'fail' | 'skip';
  }): Promise<FrozenDatasetSnapshot> => replay(api.POST('/api/trading/replay/datasets', { body: input })),
  backtests: async () =>
    (await replay(api.GET('/api/trading/replay/backtests'))).runs,
  runBacktest: (datasetId: string, input: {
    fast_period: number;
    slow_period: number;
    initial_cash: string;
    commission_bps: string;
    slippage_bps: string;
  }): Promise<BacktestRunResult> => replay(api.POST('/api/trading/replay/backtests', {
    body: {
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
    },
  })),
  backtest: (runId: string): Promise<BacktestRunResult> =>
    replay(api.GET('/api/trading/replay/backtests/{run_id}', { params: { path: { run_id: runId } } })),
  advanceExecution: (snapshot: PaperAccountSnapshot, bar: MarketBar): Promise<PaperAccountSnapshot> =>
    replay(api.POST('/api/trading/replay/execution/advance', { body: { snapshot, bar: replayBar(bar) } })),
  placeExecutionOrder: (snapshot: PaperAccountSnapshot, order: PaperOrderInput, bar: MarketBar): Promise<{ snapshot: PaperAccountSnapshot; order: PaperOrder }> =>
    replay(api.POST('/api/trading/replay/execution/orders', { body: { snapshot, order, bar: replayBar(bar) } })),
};