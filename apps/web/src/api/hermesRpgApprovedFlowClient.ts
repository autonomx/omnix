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
  error?: string | null;
  state_changed?: boolean;
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
