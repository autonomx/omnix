export interface RpgHandoffDisplayState {
  title: string;
  commandText: string;
  applied: false;
  simulationMustValidate: boolean;
  reviewRequired: boolean;
  executes: false;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function createRpgHandoffDisplayState(payload?: unknown): RpgHandoffDisplayState {
  const record = asRecord(payload);
  return {
    title: 'Proposed RPG handoff — not applied',
    commandText: typeof record.command_text === 'string' ? record.command_text : '',
    applied: false,
    simulationMustValidate: record.simulation_must_validate === true,
    reviewRequired: record.review_required !== false,
    executes: false,
  };
}
