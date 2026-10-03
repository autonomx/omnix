import type { components } from '../../api/generated/types';
import { api, unwrapLabelled } from '../../api/http';
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

export type TradingStrategyOperationsStatus = components['schemas']['StrategyOperationsStatus'];

export type AccountRiskHealth = components['schemas']['AccountRiskHealth'];

export type ExecutionHealth = components['schemas']['ExecutionHealth'];

export type TradingOperationalHealth = components['schemas']['TradingOperationalHealth'];

const operations = <T>(call: Promise<{ data?: T; error?: unknown; response: Response }>) => unwrapLabelled(call, 'Trading operations');

export const tradingStrategyOperationsApi = {
  status: (): Promise<TradingStrategyOperationsStatus> => operations(api.GET('/api/trading/strategy-operations/status')),
  solanaStrategy: (): Promise<SolanaAIStrategyRecord> => operations(api.GET('/api/trading/solana-ai/strategy')),
  solanaDecisions: async (limit = 20): Promise<SolanaAIDecisionEvent[]> =>
    (await operations(api.GET('/api/trading/solana-ai/decisions', { params: { query: { limit } } }))) as unknown as SolanaAIDecisionEvent[],
  startSolana: () => operations(api.POST('/api/trading/solana-ai/start')),
  stopSolana: () => operations(api.POST('/api/trading/solana-ai/stop')),
  health: (
    accountId: string,
    options: { instrumentId?: string | null; bindingId?: string | null } = {},
  ): Promise<TradingOperationalHealth> => operations(api.GET('/api/trading/strategy-operations/health', {
    params: {
      query: {
        account_id: accountId,
        ...(options.instrumentId ? { instrument_id: options.instrumentId } : {}),
        ...(options.bindingId ? { binding_id: options.bindingId } : {}),
      },
    },
  })),
};
