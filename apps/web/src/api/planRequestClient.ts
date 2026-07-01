import { omnixApiClient } from './client';
import type { ResultPayloadSummary } from './resultPayloadTypes';

export interface PlanRequestPayload {
  mode: 'agent_mode';
  objective: string;
  context: Record<string, unknown>;
  constraints: {
    no_execution: true;
    requires_review: true;
  };
}

export interface PlanRequestOptions {
  manualTrigger?: boolean;
}

export function planRequestPath(): `/api/${string}` {
  return '/api/agent/plan';
}

export function createPlanRequestPayload(
  objective: string,
  context: Record<string, unknown> = {},
): PlanRequestPayload {
  return {
    mode: 'agent_mode',
    objective: objective.trim(),
    context,
    constraints: {
      no_execution: true,
      requires_review: true,
    },
  };
}

export function planRequestScopeKey(scope = 'default'): string {
  return scope.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'default';
}

export function planRequestQueryKey(scope = 'default'): readonly ['plan-request', string] {
  return ['plan-request', planRequestScopeKey(scope)] as const;
}

export function canRequestPlan(options: PlanRequestOptions = {}): boolean {
  return options.manualTrigger === true;
}

export function requestPlanProposal(
  payload: PlanRequestPayload,
  options: PlanRequestOptions = {},
): Promise<ResultPayloadSummary> | null {
  if (!canRequestPlan(options)) {
    return null;
  }
  return omnixApiClient.post<PlanRequestPayload, ResultPayloadSummary>(
    planRequestPath(),
    payload,
  );
}
