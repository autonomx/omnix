import { omnixApiClient } from './client';
import type { RpgMapOverlay } from './rpgMapClient';

export interface RpgMapActionRequest {
  action: 'travel' | 'inspect' | 'enter' | 'talk' | 'trade';
  client_action_id?: string;
  definition_revision: string;
  overlay_revision: number;
  route_id?: string | null;
  target_object_id: string;
}

export interface RpgMapActionResponse {
  action_result: Record<string, unknown>;
  definition_revision: string;
  game: Record<string, unknown>;
  idempotent: boolean;
  map_id: string;
  ok: boolean;
  overlay: RpgMapOverlay;
  overlay_revision: number;
  session: Record<string, unknown>;
  session_id: string;
  session_turn_index: number;
}

export function applyRpgMapAction(
  sessionId: string,
  mapId: string,
  request: RpgMapActionRequest,
): Promise<RpgMapActionResponse> {
  return omnixApiClient.post<RpgMapActionRequest, RpgMapActionResponse>(
    `/api/rpg/sessions/${encodeURIComponent(sessionId)}/maps/${encodeURIComponent(mapId)}/map-actions`,
    request,
  );
}
