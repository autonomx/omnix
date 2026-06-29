import { omnixApiClient } from './client';

export type HermesStatusResponse = Record<string, unknown>;

export type HermesTestRequest = {
  content?: string;
  session_id?: string;
  domain?: string;
  dry_run?: boolean;
  metadata?: Record<string, unknown>;
};

export type HermesTestResponse = {
  ok?: boolean;
  dry_run?: boolean;
  result?: {
    backend?: string;
    result?: {
      response?: string;
    };
  };
  error?: string | null;
};

export function getHermesStatus(): Promise<HermesStatusResponse> {
  return omnixApiClient.get<HermesStatusResponse>('/api/hermes/status');
}

export function runHermesTest(request: HermesTestRequest = { content: 'house status', dry_run: true }): Promise<HermesTestResponse> {
  return omnixApiClient.post<HermesTestRequest, HermesTestResponse>('/api/hermes/test', request);
}
