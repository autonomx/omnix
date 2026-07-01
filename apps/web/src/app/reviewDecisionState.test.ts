import { expect, test } from 'vitest';
import { createReviewDecisionDraft } from './reviewDecisionDraft';
import { createReviewDecisionState } from './reviewDecisionState';

test('review decision state renders pending label', () => {
  expect(createReviewDecisionState(createReviewDecisionDraft('item-1'))).toEqual({
    label: 'Pending review',
    status: 'pending',
    notes: '',
    executes: false,
  });
});

test('review decision state renders approved and rejected as labels only', () => {
  expect(createReviewDecisionState(createReviewDecisionDraft('item-1', 'approved'))).toMatchObject({
    label: 'Approved label only',
    status: 'approved',
    executes: false,
  });
  expect(createReviewDecisionState(createReviewDecisionDraft('item-1', 'rejected'))).toMatchObject({
    label: 'Rejected label only',
    status: 'rejected',
    executes: false,
  });
});
