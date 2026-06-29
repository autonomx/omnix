import { omnixApiClient } from './client';

export type HermesStatusResponse = Record<string, unknown>;

export type HermesRecentResponse = {
  ok?: boolean;
  items?: Array<Record<string, unknown>>;
  count?: number;
  source?: string;
};

export type HermesCandidatePreview = {
  name?: string;
  target?: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  risk?: string;
  note?: string;
};

export type HermesCandidatePreviewResponse = {
  ok?: boolean;
  candidate?: HermesCandidatePreview;
  preview_only?: boolean;
};

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

export function getHermesRecent(): Promise<HermesRecentResponse> {
  return omnixApiClient.get<HermesRecentResponse>('/api/hermes/recent');
}

export function getHermesCandidateDemo(): Promise<HermesCandidatePreviewResponse> {
  return omnixApiClient.get<HermesCandidatePreviewResponse>('/api/hermes/candidate/demo');
}

export function runHermesTest(request: HermesTestRequest = { content: 'house status', dry_run: true }): Promise<HermesTestResponse> {
  return omnixApiClient.post<HermesTestRequest, HermesTestResponse>('/api/hermes/test', request);
}
