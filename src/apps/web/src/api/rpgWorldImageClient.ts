import type { RpgWorldSummary } from './rpgWorldLibraryClient';

export interface RpgWorldImageAttempt {
  job_id: string;
  prompt: string;
  source_content_hash: string;
  status: string;
  asset_id?: string | null;
  error: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RpgWorldImageTarget {
  world_id: string;
  target_id: string;
  target_type: string;
  entity_id: string;
  role: string;
  source_content_hash: string;
  status: string;
  review_state: string;
  suggested_prompt: string;
  active_asset_id?: string | null;
  latest_job_id?: string | null;
  metadata: Record<string, unknown>;
  attempts: RpgWorldImageAttempt[];
  created_at: string;
  updated_at: string;
}

interface RpgWorldImageTargetsResponse {
  ok: boolean;
  world: RpgWorldSummary;
  targets: RpgWorldImageTarget[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const text = await response.text();
  if (!response.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown };
      const candidate = parsed.detail ?? parsed.error;
      detail = typeof candidate === 'string' ? candidate : JSON.stringify(candidate);
    } catch {
      // Preserve raw response.
    }
    throw new Error(`Omnix API request failed with status ${response.status}${detail ? `: ${detail}` : ''}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

function json(method: string, body: Record<string, unknown>): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export const rpgWorldImageClient = {
  list(worldId: string): Promise<RpgWorldImageTargetsResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/image-targets`);
  },

  generate(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; world_id: string; jobs: Array<Record<string, unknown>> }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/image-generation`,
      json('POST', body),
    );
  },

  regeneratePrompts(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; world_id: string; targets: RpgWorldImageTarget[] }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/image-prompts/regenerate`,
      json('POST', body),
    );
  },

  update(
    worldId: string,
    targetId: string,
    body: Record<string, unknown>,
  ): Promise<RpgWorldImageTargetsResponse> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/image-targets/${encodeURIComponent(targetId)}`,
      json('PATCH', body),
    );
  },

  regenerate(
    worldId: string,
    targetId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; world_id: string; jobs: Array<Record<string, unknown>> }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/image-targets/${encodeURIComponent(targetId)}/regenerate`,
      json('POST', body),
    );
  },
};
