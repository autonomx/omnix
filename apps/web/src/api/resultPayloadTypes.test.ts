import { expect, test } from 'vitest';
import { resultReviewState, type ResultPayloadSummary } from './resultPayloadTypes';

test('result payload review state defaults to review-only', () => {
  expect(resultReviewState()).toEqual({
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});

test('result payload review state preserves explicit safe flags', () => {
  const payload: ResultPayloadSummary = {
    ok: true,
    status: 'ready',
    review_required: true,
    read_only: true,
    executes: false,
    summary: 'Review before use.',
  };

  expect(resultReviewState(payload)).toEqual({
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});
