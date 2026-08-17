import { omnixApiClient } from './client';

export type HermesRpgSequenceRequest = {
  session_id?: string;
  assist_mode?: string;
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
  checkpoint?: Record<string, unknown> | null;
  loop_guard?: Record<string, unknown> | null;
  assist_mode?: Record<string, unknown> | null;
  sequence_state?: Record<string, unknown> | null;
  state_changed?: boolean;
};

export type HermesRpgSequenceStateResponse = {
  ok?: boolean;
  source?: string;
  state?: Record<string, unknown> | null;
  error?: string | null;
};

export function checkHermesRpgSequence(
  request: HermesRpgSequenceRequest,
): Promise<HermesRpgSequenceResponse> {
  return omnixApiClient.post<HermesRpgSequenceRequest, HermesRpgSequenceResponse>(
    '/api/hermes/rpg/sequence/review',
    request,
  );
}

export function getHermesRpgSequenceState(sessionId = ''): Promise<HermesRpgSequenceStateResponse> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return omnixApiClient.get<HermesRpgSequenceStateResponse>(`/api/hermes/rpg/sequence/state${query}`);
}
