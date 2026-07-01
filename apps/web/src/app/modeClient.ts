import { modeMetadataPath } from '../api/modeMetadataClient';
import { createModeState } from './modeState';
import { createOmnixModePreview, type OmnixModePreview } from './omnixModePreview';

export interface ModeClientState {
  ok: true;
  input: string | undefined;
  fallback: boolean;
  metadataPath: `/api/${string}`;
  preview: OmnixModePreview;
}

export function readModeClientState(input: string | undefined): ModeClientState {
  const state = createModeState(input);
  return {
    ok: true,
    input,
    fallback: state.fallback,
    metadataPath: modeMetadataPath(state.id),
    preview: createOmnixModePreview(state.id),
  };
}
