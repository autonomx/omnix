import { omnixApiClient } from './client';

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
  flow?: Record<string, unknown>;
  error?: string | null;
  state_changed?: boolean;
};

export function runHermesRpgApprovedFlow(
  request: HermesRpgApprovedFlowRequest,
): Promise<HermesRpgApprovedFlowResponse> {
  return omnixApiClient.post<HermesRpgApprovedFlowRequest, HermesRpgApprovedFlowResponse>(
    '/api/hermes/rpg/approved-flow',
    request,
  );
}
