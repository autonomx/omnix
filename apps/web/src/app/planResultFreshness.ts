import { normalizePlanObjective } from './planRequestDedupe';

export interface PlanResultFreshnessKey {
  sessionId: string;
  objective: string;
  revision: number;
}

export interface PlanResultFreshnessState {
  current: boolean;
  stale: boolean;
}

export function planResultFreshnessKey(key: PlanResultFreshnessKey): string {
  return [key.sessionId.trim(), normalizePlanObjective(key.objective), String(key.revision)].join(':');
}

export function createPlanResultFreshnessState(
  expected: PlanResultFreshnessKey,
  actual: PlanResultFreshnessKey,
): PlanResultFreshnessState {
  const current = planResultFreshnessKey(expected) === planResultFreshnessKey(actual);
  return { current, stale: !current };
}
