export interface PlanStepLike {
  title?: string;
  description?: string;
}

export interface RpgCommandSuggestion {
  commandText: string;
  submits: false;
  executes: false;
}

export function createRpgCommandSuggestion(step: PlanStepLike): RpgCommandSuggestion {
  const text = [step.title, step.description]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .map((value) => value.trim())
    .join(': ');
  return {
    commandText: text,
    submits: false,
    executes: false,
  };
}
