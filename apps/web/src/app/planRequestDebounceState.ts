import { normalizePlanObjective } from './planRequestDedupe';

export interface PlanRequestDebounceState {
  normalizedObjective: string;
  ready: boolean;
  reason: 'blank' | 'waiting' | 'ready';
  autoStart: false;
}

export function createPlanRequestDebounceState(
  objective: string,
  stable: boolean,
): PlanRequestDebounceState {
  const normalizedObjective = normalizePlanObjective(objective);
  if (!normalizedObjective) {
    return { normalizedObjective, ready: false, reason: 'blank', autoStart: false };
  }
  if (!stable) {
    return { normalizedObjective, ready: false, reason: 'waiting', autoStart: false };
  }
  return { normalizedObjective, ready: true, reason: 'ready', autoStart: false };
}
