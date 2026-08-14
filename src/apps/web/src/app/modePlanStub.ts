import type { OmnixModeId } from './omnixModeIds';

export interface ModePlanStub {
  ok: true;
  mode: OmnixModeId;
  label: string;
  reviewRequired: boolean;
}

export function readModePlanStub(mode: OmnixModeId): ModePlanStub {
  return {
    ok: true,
    mode,
    label: 'Adapter',
    reviewRequired: mode === 'agent',
  };
}
