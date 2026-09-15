type CachedIdentity = {
  characterId: string | null;
  expiresAtMs: number;
};

type SessionIdentityPayload = {
  interaction_mode?: unknown;
  character_id?: unknown;
};

const CACHE_TTL_MS = 5_000;
const cache = new Map<string, CachedIdentity>();
const inFlight = new Map<string, Promise<string | null>>();

export async function resolveDesktopCompanionCharacterId(
  sessionId: string,
  nowMs = Date.now(),
): Promise<string | null> {
  const normalized = sessionId.trim();
  if (!normalized) return null;
  const cached = cache.get(normalized);
  if (cached && nowMs < cached.expiresAtMs) return cached.characterId;
  const active = inFlight.get(normalized);
  if (active) return active;

  const request = fetch(`/api/chat/sessions/${encodeURIComponent(normalized)}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
    .then(async (response) => {
      if (!response.ok) return null;
      const payload = await response.json() as SessionIdentityPayload;
      if (payload.interaction_mode !== 'character') return null;
      return typeof payload.character_id === 'string' && payload.character_id.trim()
        ? payload.character_id.trim()
        : null;
    })
    .catch(() => null)
    .then((characterId) => {
      cache.set(normalized, {
        characterId,
        expiresAtMs: Date.now() + CACHE_TTL_MS,
      });
      return characterId;
    })
    .finally(() => {
      if (inFlight.get(normalized) === request) inFlight.delete(normalized);
    });
  inFlight.set(normalized, request);
  return request;
}

export function invalidateDesktopCompanionSessionIdentity(sessionId?: string): void {
  if (sessionId) cache.delete(sessionId.trim());
  else cache.clear();
}
