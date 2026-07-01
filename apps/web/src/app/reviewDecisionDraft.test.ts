import { expect, test } from 'vitest';
import { createReviewDecisionDraft, validateReviewDecisionDraft } from './reviewDecisionDraft';

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

test('review decision validation accepts known decision labels only', () => {
  expect(validateReviewDecisionDraft(createReviewDecisionDraft('item-1', 'rejected'))).toEqual({
    ok: true,
    errors: [],
    executes: false,
  });
});

test('review decision validation rejects missing item id and unknown decision', () => {
  expect(validateReviewDecisionDraft({ item_id: '', decision: 'maybe' as never })).toEqual({
    ok: false,
    errors: ['item_id_required', 'unknown_decision'],
    executes: false,
  });
});
