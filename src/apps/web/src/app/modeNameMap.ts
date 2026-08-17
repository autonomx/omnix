import type { OmnixModeId } from './omnixModeIds';

export type BackendModeId = 'normal_chat' | 'live_chat' | 'agent_mode' | 'house_ai' | 'podcast' | 'rpg';

const FRONTEND_TO_BACKEND: Record<OmnixModeId, BackendModeId> = {
  normal: 'normal_chat',
  live: 'live_chat',
  agent: 'agent_mode',
  house: 'house_ai',
  podcast: 'podcast',
  rpg: 'rpg',
};

const BACKEND_TO_FRONTEND: Record<BackendModeId, OmnixModeId> = {
  normal_chat: 'normal',
  live_chat: 'live',
  agent_mode: 'agent',
  house_ai: 'house',
  podcast: 'podcast',
  rpg: 'rpg',
};

export function toBackendModeId(mode: OmnixModeId): BackendModeId {
  return FRONTEND_TO_BACKEND[mode];
}

export function toFrontendModeId(mode: BackendModeId): OmnixModeId {
  return BACKEND_TO_FRONTEND[mode];
}
