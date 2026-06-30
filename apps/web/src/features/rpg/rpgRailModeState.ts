export interface RpgRailModeState {
  mode: string;
  role: string;
  owner: string;
  reviewRequired: boolean;
  boundary: string;
}

export function createRpgRailModeState(payload: Record<string, unknown> | undefined): RpgRailModeState | undefined {
  if (payload?.ok !== true) return undefined;
  return {
    mode: typeof payload.mode === 'string' ? payload.mode : 'rpg',
    role: typeof payload.role === 'string' ? payload.role : 'suggest',
    owner: typeof payload.owner === 'string' ? payload.owner : 'rpg_sim',
    reviewRequired: payload.review_required === true,
    boundary: typeof payload.boundary === 'string' ? payload.boundary : 'RPG simulation validates truth before state is accepted.',
  };
}
