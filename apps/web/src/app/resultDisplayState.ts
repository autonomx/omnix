import { resultReviewState, type ResultPayloadSummary } from '../api/resultPayloadTypes';

export interface ResultDisplayState {
  title: string;
  detail: string;
  status: 'ready' | 'unavailable';
  reviewRequired: boolean;
  readOnly: boolean;
  executes: boolean;
}

function isResultPayload(value: unknown): value is ResultPayloadSummary {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function createResultDisplayState(payload?: unknown): ResultDisplayState {
  if (!isResultPayload(payload)) {
    return {
      title: 'Needs review',
      detail: 'No proposal payload is available yet.',
      status: 'unavailable',
      reviewRequired: true,
      readOnly: true,
      executes: false,
    };
  }

  const review = resultReviewState(payload);
  const ready = payload.ok === true;
  return {
    title: ready ? 'Ready for review' : 'Needs review',
    detail: payload.summary || payload.error || payload.status || 'Review before use.',
    status: ready ? 'ready' : 'unavailable',
    reviewRequired: review.reviewRequired,
    readOnly: review.readOnly,
    executes: review.executes,
  };
}
