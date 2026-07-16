export interface RpgWorldSummary {
  id: string;
  title: string;
  description: string;
  status: string;
  source_mode: string;
  genre: string;
  tone: string;
  seed: number;
  draft_revision: number;
  metadata: Record<string, unknown>;
  scenario_count?: number;
  generation?: RpgWorldGenerationRun | null;
  created_at: string;
  updated_at: string;
}

export interface RpgScenarioSummary {
  id: string;
  world_id: string;
  title: string;
  description: string;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RpgWorldCampaignSummary {
  campaign_id: string;
  title: string;
  status: string;
  revision: number;
  updated_at: string;
  world_id: string;
  world_revision: number;
  world_release: number;
  scenario_id: string;
  scenario_revision: number;
  binding: Record<string, unknown>;
}

export interface RpgWorldGenerationRun {
  run_id: string;
  world_id: string;
  draft_revision: number;
  status: string;
  graph: Record<string, unknown>;
  context: Record<string, unknown>;
  settings: Record<string, unknown>;
  plan: Record<string, unknown>;
  progress: Record<string, unknown>;
  error: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface RpgWorldTopic {
  topic_id: string;
  draft_revision: number;
  source: string;
  status: string;
  content: Record<string, unknown>;
  directives: Record<string, unknown>;
  dependency_hashes: Record<string, string>;
  input_hash: string;
  content_hash: string;
  provenance: Record<string, unknown>;
  updated_at: string;
}

export interface RpgWorldRevision {
  revision: number;
  document: Record<string, unknown>;
  content_hash: string;
  created_at: string;
}

export interface RpgWorldRelease {
  world_revision: number;
  release: number;
  document: Record<string, unknown>;
  release_hash: string;
  created_at: string;
}

export interface RpgScenarioRevision {
  revision: number;
  world_id: string;
  world_revision: number;
  document: Record<string, unknown>;
  content_hash: string;
  created_at: string;
}

export interface RpgWorldLibraryResponse {
  ok: boolean;
  worlds: RpgWorldSummary[];
  scenarios: RpgScenarioSummary[];
  campaigns: RpgWorldCampaignSummary[];
  generation_runs: RpgWorldGenerationRun[];
}

export interface RpgWorldDetailResponse {
  ok: boolean;
  world: RpgWorldSummary;
  topics: RpgWorldTopic[];
  revisions: RpgWorldRevision[];
  releases: RpgWorldRelease[];
  scenarios: RpgScenarioSummary[];
  scenario_revisions: Record<string, RpgScenarioRevision[]>;
  generation_runs: RpgWorldGenerationRun[];
}

export interface RpgPublishedLaunchResponse {
  ok: boolean;
  status?: string;
  session_id?: string;
  session?: Record<string, unknown>;
  game?: Record<string, unknown>;
  binding?: Record<string, unknown>;
  launch_mode?: string;
  world_forge_invoked?: boolean;
  error?: string;
}

export interface RpgStarterBubbleResponse {
  ok: boolean;
  starter_bubble: Record<string, unknown>;
  predictive_materialization: Record<string, unknown>[];
}

export interface RpgStarterBubblePromotionResponse {
  ok: boolean;
  status: string;
  reused: boolean;
  promotion: Record<string, unknown>;
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
      // Preserve the raw response body.
    }
    throw new Error(`Omnix API request failed with status ${response.status}${detail ? `: ${detail}` : ''}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

function jsonInit(body: Record<string, unknown>): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export const rpgWorldLibraryClient = {
  list(): Promise<RpgWorldLibraryResponse> {
    return request<RpgWorldLibraryResponse>('/api/rpg/world-library');
  },

  detail(worldId: string): Promise<RpgWorldDetailResponse> {
    return request<RpgWorldDetailResponse>(`/api/rpg/worlds/${encodeURIComponent(worldId)}/library`);
  },

  createWorld(body: Record<string, unknown>): Promise<{ ok: boolean; world: RpgWorldSummary }> {
    return request('/api/rpg/worlds', jsonInit(body));
  },

  saveTopic(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; topic: RpgWorldTopic }> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/topics`, jsonInit(body));
  },

  startGeneration(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; run: RpgWorldGenerationRun; worker_started: boolean }> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/generation`, jsonInit(body));
  },

  generation(runId: string): Promise<{ ok: boolean; run: RpgWorldGenerationRun }> {
    return request(`/api/rpg/world-generation/${encodeURIComponent(runId)}`);
  },

  publishGeneration(
    runId: string,
  ): Promise<{ ok: boolean; status: string; run: RpgWorldGenerationRun; publication: Record<string, unknown> }> {
    return request(`/api/rpg/world-generation/${encodeURIComponent(runId)}/publish`, jsonInit({}));
  },

  previewStarterBubble(
    worldId: string,
    sourceWorldRevision: number,
    startingLocationId: string,
    neighboringLocationId?: string,
  ): Promise<RpgStarterBubbleResponse> {
    const query = new URLSearchParams({
      source_world_revision: String(sourceWorldRevision),
      starting_location_id: startingLocationId,
    });
    if (neighboringLocationId) query.set('neighboring_location_id', neighboringLocationId);
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/starter-bubble/preview?${query.toString()}`,
    );
  },

  promoteStarterBubble(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<RpgStarterBubblePromotionResponse> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/starter-bubble/promote`,
      jsonInit(body),
    );
  },

  createScenario(body: Record<string, unknown>): Promise<{ ok: boolean; scenario: RpgScenarioSummary }> {
    return request('/api/rpg/scenarios', jsonInit(body));
  },

  publishScenario(
    scenarioId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; scenario_revision: RpgScenarioRevision }> {
    return request(`/api/rpg/scenarios/${encodeURIComponent(scenarioId)}/revisions`, jsonInit(body));
  },

  launchScenario(
    scenarioId: string,
    scenarioRevision: number,
    body: Record<string, unknown>,
  ): Promise<RpgPublishedLaunchResponse> {
    return request(
      `/api/rpg/scenarios/${encodeURIComponent(scenarioId)}/revisions/${scenarioRevision}/launch`,
      jsonInit(body),
    );
  },
};
