export interface PlanManualTriggerGuardInput {
  ready?: boolean;
  manualTrigger?: boolean;
}

export interface PlanManualTriggerGuardState {
  canStart: boolean;
  reason: 'not_ready' | 'manual_required' | 'ready';
  autoStart: false;
}

export function createPlanManualTriggerGuard(
  input: PlanManualTriggerGuardInput = {},
): PlanManualTriggerGuardState {
  if (!input.ready) {
    return { canStart: false, reason: 'not_ready', autoStart: false };
  }
  if (input.manualTrigger !== true) {
    return { canStart: false, reason: 'manual_required', autoStart: false };
  }
  return { canStart: true, reason: 'ready', autoStart: false };
}
