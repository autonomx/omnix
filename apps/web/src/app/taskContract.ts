import type { OmnixModeId } from './omnixModeIds';

export interface TaskContract {
  ok: true;
  mode: OmnixModeId;
  text: string;
  review: boolean;
}

export function makeTaskContract(mode: OmnixModeId, text: string): TaskContract {
  return {
    ok: true,
    mode,
    text: text.trim() || 'No input provided.',
    review: mode === 'agent',
  };
}
