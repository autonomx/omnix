import { expect, test } from 'vitest';
import {
  canRequestPlan,
  createPlanRequestPayload,
  planRequestPath,
  planRequestQueryKey,
  planRequestScopeKey,
  requestPlanProposal,
} from './planRequestClient';

test('plan request path is stable', () => {
  expect(planRequestPath()).toBe('/api/agent/plan');
});

test('plan request payload keeps review and no-execution constraints', () => {
  expect(createPlanRequestPayload('  review next step  ', { mode: 'rpg' })).toEqual({
    mode: 'agent_mode',
    objective: 'review next step',
    context: { mode: 'rpg' },
    constraints: {
      no_execution: true,
      requires_review: true,
    },
  });
});

test('plan request is manual-trigger gated by default', () => {
  const payload = createPlanRequestPayload('review');

  expect(canRequestPlan()).toBe(false);
  expect(requestPlanProposal(payload)).toBeNull();
  expect(canRequestPlan({ manualTrigger: true })).toBe(true);
});

test('plan request query keys use stable scope instead of raw objective', () => {
  expect(planRequestScopeKey(' RPG Session 1 ')).toBe('rpg-session-1');
  expect(planRequestScopeKey('')).toBe('default');
  expect(planRequestQueryKey(' RPG Session 1 ')).toEqual(['plan-request', 'rpg-session-1']);
});
