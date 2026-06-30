import { getOmnixModeInfo, type OmnixModeId } from './omnixModeIds';
import { getOmnixModeRoute, type OmnixModePath } from './omnixModeRouter';

export interface OmnixModePreview {
  mode: OmnixModeId;
  label: string;
  path: OmnixModePath;
  owner: string;
  status: 'ready' | 'review';
  statusLabel: string;
}

export function createOmnixModePreview(mode: OmnixModeId): OmnixModePreview {
  const info = getOmnixModeInfo(mode);
  const route = getOmnixModeRoute(mode);
  return {
    mode,
    label: info.label,
    path: route.path,
    owner: route.owner,
    status: route.needsReview ? 'review' : 'ready',
    statusLabel: route.needsReview ? 'Review required' : 'Ready',
  };
}
