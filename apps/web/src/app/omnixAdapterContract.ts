import type { OmnixModeId } from './omnixModeIds';

export interface OmnixAdapterRequest {
  mode: OmnixModeId;
  input: string;
  context?: Record<string, unknown>;
}

export interface OmnixAdapterPlan {
  id: string;
  label: string;
  summary: string;
  reviewRequired: boolean;
}

export interface OmnixAdapterResult {
  ok: boolean;
  mode: OmnixModeId;
  plan?: OmnixAdapterPlan;
  error?: string;
}

export function createAgentAdapterPlaceholder(request: OmnixAdapterRequest): OmnixAdapterResult {
  if (request.mode !== 'agent') {
    return { ok: false, mode: request.mode, error: 'unsupported_mode' };
  }

  return {
    ok: true,
    mode: 'agent',
    plan: {
      id: 'agent-placeholder',
      label: 'Agent adapter',
      summary: request.input.trim() || 'No input provided.',
      reviewRequired: true,
    },
  };
}
