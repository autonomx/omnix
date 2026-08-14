export interface ResultPayloadFlags {
  ok?: boolean;
  read_only?: boolean;
  executes?: boolean;
  review_required?: boolean;
}

export interface ResultPayloadSummary extends ResultPayloadFlags {
  status?: string;
  summary?: string;
  response?: unknown;
  error?: string | null;
}

export interface ResultReviewState {
  reviewRequired: boolean;
  readOnly: boolean;
  executes: boolean;
}

export function resultReviewState(payload?: ResultPayloadFlags | null): ResultReviewState {
  return {
    reviewRequired: payload?.review_required ?? true,
    readOnly: payload?.read_only ?? true,
    executes: payload?.executes ?? false,
  };
}
