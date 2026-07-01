import { expect, test } from 'vitest';
import { createAuditDisplayState } from './auditDisplayState';

test('audit display state exposes compact safe audit fields', () => {
  expect(
    createAuditDisplayState({
      source: 'plan_request',
      timestamp: '2026-01-01T00:00:00Z',
      detail: { token: 'hidden' },
      read_only: true,
      executes: false,
      review_required: true,
    }),
  ).toEqual({
    source: 'plan_request',
    status: 'ready',
    timestamp: '2026-01-01T00:00:00Z',
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});

test('audit display state handles missing payload safely', () => {
  expect(createAuditDisplayState()).toEqual({
    source: 'unknown',
    status: 'unavailable',
    timestamp: '',
    reviewRequired: true,
    readOnly: true,
    executes: false,
  });
});
