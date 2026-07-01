import { expect, test } from 'vitest';
import { createPlanResultFreshnessState, planResultFreshnessKey } from './planResultFreshness';

test('plan result freshness key is deterministic', () => {
  expect(planResultFreshnessKey({ sessionId: ' s1 ', objective: ' Review  Step ', revision: 2 })).toBe(
    's1:review step:2',
  );
});

test('plan result freshness detects current matching input', () => {
  const key = { sessionId: 's1', objective: 'review step', revision: 2 };
  expect(createPlanResultFreshnessState(key, { ...key, objective: ' Review  Step ' })).toEqual({
    current: true,
    stale: false,
  });
});

test('plan result freshness detects stale revision changes', () => {
  expect(
    createPlanResultFreshnessState(
      { sessionId: 's1', objective: 'review step', revision: 2 },
      { sessionId: 's1', objective: 'review step', revision: 1 },
    ),
  ).toEqual({ current: false, stale: true });
});
