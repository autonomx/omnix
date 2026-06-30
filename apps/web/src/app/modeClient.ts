import { createModeState } from './modeState';
import { createOmnixModePreview, type OmnixModePreview } from './omnixModePreview';

export interface ModeClientState {
  ok: true;
  input: string | undefined;
  fallback: boolean;
  preview: OmnixModePreview;
}

export function readModeClientState(input: string | undefined): ModeClientState {
  const state = createModeState(input);
  return {
    ok: true,
    input,
    fallback: state.fallback,
    preview: createOmnixModePreview(state.id),
  };
}
