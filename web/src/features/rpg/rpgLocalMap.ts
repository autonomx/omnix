import type { RpgSession } from './rpgUiTypes';

export interface RpgLocalMap {
  heroName: string;
  mapInstanceId: string;
  playerActorId: string;
}

function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function heroNameFrom(state: Record<string, unknown>): string {
  for (const key of ['player', 'hero', 'character']) {
    const name = recordOf(state[key]).name;
    if (typeof name === 'string' && name.trim()) return name.trim();
  }
  return 'You';
}

/** The local map a session launched from a published world stands on, and who the hero is on its grid. */
export function rpgLocalMap(session: RpgSession | Record<string, unknown> | undefined, sessionId: string): RpgLocalMap {
  const state = recordOf(recordOf(session).state);
  const mapInstanceId = typeof state.current_map_instance_id === 'string' ? state.current_map_instance_id.trim() : '';
  return {
    heroName: heroNameFrom(state),
    mapInstanceId,
    playerActorId: mapInstanceId ? `player:${sessionId}` : '',
  };
}
