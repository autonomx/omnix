import { expect, test } from 'vitest';
import { createPlanRequestState } from './planRequestState';

test('plan request state starts idle and non-executing', () => {
  expect(createPlanRequestState()).toEqual({
    status: 'idle',
    canRequest: true,
    reviewRequired: true,
    executes: false,
    message: 'Request a proposal when ready.',
  });
});

test('plan request state blocks duplicate requests while loading', () => {
  expect(createPlanRequestState({ pending: true })).toMatchObject({
    status: 'loading',
    canRequest: false,
    reviewRequired: true,
    executes: false,
  });
});

test('plan request state becomes ready without enabling execution', () => {
  expect(
    createPlanRequestState({
      payload: {
        ok: true,
        summary: 'Review the proposal.',
        review_required: true,
        executes: false,
      },
    }),
  ).toEqual({
    status: 'ready',
    canRequest: true,
    reviewRequired: true,
    executes: false,
    message: 'Review the proposal.',
  });
});

test('plan request state records errors without execution', () => {
  expect(createPlanRequestState({ error: 'Unavailable' })).toMatchObject({
    status: 'error',
    canRequest: true,
    reviewRequired: true,
    executes: false,
    message: 'Unavailable',
  });
});
