import { getOmnixModeInfo, isOmnixModeId, type OmnixModeId } from './omnixModeIds';

export interface ModeState {
  id: OmnixModeId;
  label: string;
  fallback: boolean;
}

export function createModeState(value: string | undefined, fallbackId: OmnixModeId = 'normal'): ModeState {
  const id = isOmnixModeId(value) ? value : fallbackId;
  return {
    id,
    label: getOmnixModeInfo(id).label,
    fallback: id !== value,
  };
}
