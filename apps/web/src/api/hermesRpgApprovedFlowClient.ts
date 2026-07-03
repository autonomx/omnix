import { omnixApiClient } from './client';

export type HermesRpgApprovedFlowConfig = {
  ok?: boolean;
  source?: string;
  feature_flag?: string;
  default_enabled?: boolean;
  enabled?: boolean;
  requires_payload_enabled?: boolean;
  simulation_owned?: boolean;
};

export type HermesRpgApprovedFlowRequest = {
  enabled?: boolean;
  user_step?: Record<string, unknown>;
  replay_entry?: Record<string, unknown>;
  context?: Record<string, unknown>;
};

export type HermesRpgApprovedFlowResponse = {
  ok?: boolean;
  source?: string;
  enabled?: boolean;
  config?: HermesRpgApprovedFlowConfig;
  flow?: Record<string, unknown>;
  readout?: Record<string, unknown>;
  ledger_entry?: Record<string, unknown>;
  error?: string | null;
  state_changed?: boolean;
};

export type HermesRpgExecutionLedgerItem = {
  execution_id?: string;
  created_at?: string;
  session_id?: string | null;
  sequence_id?: string | null;
  item_id?: string | null;
  command_text?: string | null;
  approval_source?: string | null;
  checkpoint_reason?: string | null;
  state_changed?: boolean;
  result_summary?: string | null;
  error?: string | null;
};

export type HermesRpgExecutionLedgerResponse = {
  ok?: boolean;
  source?: string;
  items?: HermesRpgExecutionLedgerItem[];
  count?: number;
};

export function getHermesRpgApprovedFlowConfig(): Promise<HermesRpgApprovedFlowConfig> {
  return omnixApiClient.get<HermesRpgApprovedFlowConfig>('/api/hermes/rpg/approved-flow/config');
}

export function runHermesRpgApprovedFlow(
  request: HermesRpgApprovedFlowRequest,
): Promise<HermesRpgApprovedFlowResponse> {
  return omnixApiClient.post<HermesRpgApprovedFlowRequest, HermesRpgApprovedFlowResponse>(
    '/api/hermes/rpg/approved-flow',
    request,
  );
}

export function getHermesRpgExecutionLedger(params: { limit?: number; sessionId?: string; sequenceId?: string } = {}): Promise<HermesRpgExecutionLedgerResponse> {
  const query = new URLSearchParams();
  if (params.limit) query.set('limit', String(params.limit));
  if (params.sessionId) query.set('session_id', params.sessionId);
  if (params.sequenceId) query.set('sequence_id', params.sequenceId);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return omnixApiClient.get<HermesRpgExecutionLedgerResponse>(`/api/hermes/rpg/approved-flow/ledger${suffix}`);
}
