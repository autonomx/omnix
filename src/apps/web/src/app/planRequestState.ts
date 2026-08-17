import type { ResultPayloadSummary } from '../api/resultPayloadTypes';

export type PlanRequestStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface PlanRequestStateInput {
  pending?: boolean;
  payload?: ResultPayloadSummary | null;
  error?: string | null;
}

export interface PlanRequestState {
  status: PlanRequestStatus;
  canRequest: boolean;
  reviewRequired: boolean;
  executes: false;
  message: string;
}

export function createPlanRequestState(input: PlanRequestStateInput = {}): PlanRequestState {
  if (input.pending) {
    return {
      status: 'loading',
      canRequest: false,
      reviewRequired: true,
      executes: false,
      message: 'Proposal request is in progress.',
    };
  }

  if (input.error) {
    return {
      status: 'error',
      canRequest: true,
      reviewRequired: true,
      executes: false,
      message: input.error,
    };
  }

  if (input.payload?.ok === true) {
    return {
      status: 'ready',
      canRequest: true,
      reviewRequired: input.payload.review_required ?? true,
      executes: false,
      message: input.payload.summary || 'Proposal is ready for review.',
    };
  }

  return {
    status: 'idle',
    canRequest: true,
    reviewRequired: true,
    executes: false,
    message: 'Request a proposal when ready.',
  };
}
