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

export type HermesApprovalRequest = {
  candidate?: HermesCandidatePreview | null;
  preview_only?: boolean;
};

export type HermesApprovalResponse = {
  ok?: boolean;
  approved?: boolean;
  error?: string | null;
  mode?: string;
  request?: Record<string, unknown>;
};

export type HermesRouteDecisionResponse = {
  ok?: boolean;
  source?: string;
  mode?: string;
  role?: string;
  owner?: string;
  review_required?: boolean;
  capabilities?: string[];
  boundary?: string;
  error?: string | null;
};

export type HermesRpgSuggestion = {
  id?: string;
  label?: string;
  command?: string;
  kind?: string;
  risk?: string;
  requires_user_click?: boolean;
  direct_state_write?: boolean;
  processed_by?: string;
  reason?: string;
};

export type HermesRpgSuggestionsRequest = {
  session_id?: string;
  context?: Record<string, unknown>;
};

export type HermesRpgSuggestionsResponse = {
  ok?: boolean;
  read_only?: boolean;
  source?: string;
  suggestions?: HermesRpgSuggestion[];
  count?: number;
  error?: string | null;
};

export type HermesRpgTurnReadoutRequest = {
  session_id?: string;
  turn?: Record<string, unknown>;
  context?: Record<string, unknown>;
};

export type HermesRpgTurnReadoutResponse = {
  ok?: boolean;
  read_only?: boolean;
  source?: string;
  session_id?: string | null;
  turn?: {
    turn_id?: string | number | null;
    command?: string;
    category?: string;
    narration_present?: boolean;
  };
  systems?: string[];
  effect_count?: number;
  grounding_status?: string;
  notes?: string[];
  error?: string | null;
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

export function getHermesRouteDecision(mode = 'rpg'): Promise<HermesRouteDecisionResponse> {
  return omnixApiClient.get<HermesRouteDecisionResponse>(`/api/hermes/route-decision?mode=${encodeURIComponent(mode)}`);
}

export function approveHermesCandidate(request: HermesApprovalRequest): Promise<HermesApprovalResponse> {
  return omnixApiClient.post<HermesApprovalRequest, HermesApprovalResponse>('/api/hermes/approve', request);
}

export function getHermesRpgSuggestions(request: HermesRpgSuggestionsRequest): Promise<HermesRpgSuggestionsResponse> {
  return omnixApiClient.post<HermesRpgSuggestionsRequest, HermesRpgSuggestionsResponse>('/api/hermes/rpg/suggestions', request);
}

export function readHermesRpgTurn(request: HermesRpgTurnReadoutRequest): Promise<HermesRpgTurnReadoutResponse> {
  return omnixApiClient.post<HermesRpgTurnReadoutRequest, HermesRpgTurnReadoutResponse>('/api/hermes/rpg/turn-readout', request);
}

export function runHermesTest(request: HermesTestRequest = { content: 'house status', dry_run: true }): Promise<HermesTestResponse> {
  return omnixApiClient.post<HermesTestRequest, HermesTestResponse>('/api/hermes/test', request);
}
