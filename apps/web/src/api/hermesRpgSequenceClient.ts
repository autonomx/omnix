import { omnixApiClient } from './client';

export type HermesRpgSequenceRequest = {
  sequence_id?: string;
  objective?: string;
  domain?: string;
  state_owner?: string;
  risk?: string;
  status?: string;
  items?: Array<Record<string, unknown>>;
};

export type HermesRpgSequenceResponse = {
  ok?: boolean;
  source?: string;
  validation?: Record<string, unknown>;
  sequence?: Record<string, unknown>;
  gate?: Record<string, unknown> | null;
  state_changed?: boolean;
};

export function checkHermesRpgSequence(
  request: HermesRpgSequenceRequest,
): Promise<HermesRpgSequenceResponse> {
  return omnixApiClient.post<HermesRpgSequenceRequest, HermesRpgSequenceResponse>(
    '/api/hermes/rpg/sequence/review',
    request,
  );
}
