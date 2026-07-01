import { expect, test } from 'vitest';
import { createReviewDecisionDraft } from './reviewDecisionDraft';

test('review decision draft defaults to pending and non-executing', () => {
  expect(createReviewDecisionDraft(' item-1 ')).toEqual({
    item_id: 'item-1',
    decision: 'pending',
    notes: '',
    executes: false,
  });
});

test('review decision draft stores labels and notes without execution', () => {
  expect(createReviewDecisionDraft('item-1', 'approved', ' Looks safe. ')).toEqual({
    item_id: 'item-1',
    decision: 'approved',
    notes: 'Looks safe.',
    executes: false,
  });
});
