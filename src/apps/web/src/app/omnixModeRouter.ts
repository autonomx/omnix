import type { OmnixModeId } from './omnixModeIds';

export type OmnixModePath = 'direct' | 'live' | 'adapter' | 'review' | 'audio' | 'sim';

export interface OmnixModeRoute {
  mode: OmnixModeId;
  path: OmnixModePath;
  owner: string;
  needsReview: boolean;
}

const MODE_ROUTES: Record<OmnixModeId, OmnixModeRoute> = {
  normal: { mode: 'normal', path: 'direct', owner: 'provider', needsReview: false },
  live: { mode: 'live', path: 'live', owner: 'voice', needsReview: false },
  agent: { mode: 'agent', path: 'adapter', owner: 'hermes', needsReview: true },
  house: { mode: 'house', path: 'review', owner: 'omnix', needsReview: true },
  podcast: { mode: 'podcast', path: 'audio', owner: 'omnix', needsReview: true },
  rpg: { mode: 'rpg', path: 'sim', owner: 'rpg_sim', needsReview: false },
};

export function getOmnixModeRoute(mode: OmnixModeId): OmnixModeRoute {
  return MODE_ROUTES[mode];
}

export function usesExistingOmnixPath(mode: OmnixModeId): boolean {
  const route = getOmnixModeRoute(mode);
  return route.path === 'direct' || route.path === 'live';
}
