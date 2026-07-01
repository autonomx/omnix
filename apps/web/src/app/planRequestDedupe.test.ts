import { expect, test } from 'vitest';
import { hasPendingPlanRequest, normalizePlanObjective } from './planRequestDedupe';

test('plan objective normalization trims spacing and case', () => {
  expect(normalizePlanObjective('  Review   Next Step  ')).toBe('review next step');
});

test('pending plan request dedupe detects identical normalized objectives', () => {
  const pending = [{ id: 'p1', objective: 'Review next step' }];

  expect(hasPendingPlanRequest(pending, ' review   NEXT step ')).toBe(true);
  expect(hasPendingPlanRequest(pending, 'inspect inventory')).toBe(false);
});
