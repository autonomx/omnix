export interface RpgWorldProfilePresentation {
  page_kind?: 'document' | 'collection' | string;
  card_variant?: string;
  image_role?: string;
  group?: 'world' | 'lore' | 'game-master' | string;
}

export interface RpgWorldProfileTargetRange {
  quick?: number[];
  standard?: number[];
  epic?: number[];
}

export interface RpgWorldProfileDomain {
  domain_id: string;
  title: string;
  entity_kind: string;
  dependencies?: string[];
  required_before_launch?: boolean;
  fields?: Array<Record<string, unknown>>;
  target_range?: RpgWorldProfileTargetRange;
  semantic_roles?: string[];
  generation_guidance?: {
    presentation?: RpgWorldProfilePresentation;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface RpgWorldGenreProfile {
  profile_id: string;
  version: number;
  display_name: string;
  domains: RpgWorldProfileDomain[];
  aliases?: string[];
  genre_tags?: string[];
  launch_requirements?: Record<string, unknown>;
  runtime_capability_defaults?: Record<string, boolean>;
  provenance?: Record<string, unknown>;
  scope?: string;
  [key: string]: unknown;
}

export interface RpgWorldProfileReview {
  world_id: string;
  status: string;
  profile_revision: number;
  profile_hash: string;
  approved_profile_hash: string;
  approved_at?: string | null;
  approved_by?: string | null;
  profile: RpgWorldGenreProfile | Record<string, never>;
  requested_genre: string;
  normalized_genre: string;
  source: string;
  generated: boolean;
  route: Record<string, unknown>;
  review_findings: unknown[];
  error: Record<string, unknown>;
}

interface RpgWorldProfileResponse {
  ok: boolean;
  review: RpgWorldProfileReview;
  stale_topic_ids?: string[];
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

function json(method: 'PATCH' | 'POST', body: Record<string, unknown>): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

function profilePath(worldId: string): string {
  return `/api/rpg/worlds/${encodeURIComponent(worldId)}/genre-profile`;
}

export const rpgWorldProfileClient = {
  read(worldId: string): Promise<RpgWorldProfileResponse> {
    return request(profilePath(worldId));
  },

  update(
    worldId: string,
    expectedProfileRevision: number,
    profile: RpgWorldGenreProfile,
  ): Promise<RpgWorldProfileResponse> {
    return request(profilePath(worldId), json('PATCH', {
      expected_profile_revision: expectedProfileRevision,
      profile,
    }));
  },

  approve(
    worldId: string,
    expectedProfileRevision: number,
  ): Promise<RpgWorldProfileResponse> {
    return request(`${profilePath(worldId)}/approve`, json('POST', {
      expected_profile_revision: expectedProfileRevision,
    }));
  },

  retry(worldId: string): Promise<RpgWorldProfileResponse> {
    return request(`${profilePath(worldId)}/retry`, { method: 'POST' });
  },
};
