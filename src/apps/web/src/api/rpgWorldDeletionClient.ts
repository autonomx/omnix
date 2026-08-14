export interface RpgWorldDeletionBlocker {
  code: string;
  count: number;
  message: string;
}

export interface RpgWorldDeletionEligibility {
  can_delete: boolean;
  world_id: string;
  world_title: string;
  world_status: string;
  blockers: RpgWorldDeletionBlocker[];
  deleted_counts: Record<string, number>;
}

interface RpgWorldDeletionEligibilityResponse {
  ok: boolean;
  eligibility: RpgWorldDeletionEligibility;
}

export interface RpgWorldDeletionResponse {
  ok: boolean;
  deleted: boolean;
  world_id: string;
  world_title: string;
  deleted_counts: Record<string, number>;
  audit_event_id: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const text = await response.text();
  if (!response.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown };
      const candidate = parsed.detail ?? parsed.error;
      if (candidate && typeof candidate === 'object' && 'error' in candidate) {
        detail = String((candidate as { error: unknown }).error);
      } else {
        detail = typeof candidate === 'string' ? candidate : JSON.stringify(candidate);
      }
    } catch {
      // Preserve the raw response.
    }
    throw new Error(`Omnix API request failed with status ${response.status}${detail ? `: ${detail}` : ''}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

export const rpgWorldDeletionClient = {
  eligibility(worldId: string): Promise<RpgWorldDeletionEligibilityResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/deletion-eligibility`);
  },

  delete(worldId: string, confirmationTitle: string): Promise<RpgWorldDeletionResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        confirmation_title: confirmationTitle,
        acknowledge_permanent: true,
      }),
    });
  },
};
