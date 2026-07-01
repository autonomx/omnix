import { expect, test } from 'vitest';
import { createResultDisplayState } from './resultDisplayState';

test('result display state handles empty payloads as review-only unavailable', () => {
  expect(createResultDisplayState()).toEqual({
    title: 'Needs review',
    detail: 'No proposal payload is available yet.',
    status: 'unavailable',
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});

test('result display state handles malformed payloads safely', () => {
  expect(createResultDisplayState(['bad'])).toMatchObject({
    status: 'unavailable',
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});

test('result display state maps ready payloads to review cards', () => {
  expect(
    createResultDisplayState({
      ok: true,
      summary: 'Review the suggested next step.',
      review_required: true,
      read_only: true,
      executes: false,
    }),
  ).toEqual({
    title: 'Ready for review',
    detail: 'Review the suggested next step.',
    status: 'ready',
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});
