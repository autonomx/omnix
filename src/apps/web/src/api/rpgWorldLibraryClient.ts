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
  parent_run_id?: string | null;
  lineage?: Record<string, unknown>;
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

export interface RpgMapBlueprintRevision {
  world_id: string;
  map_id: string;
  blueprint_revision: number;
  document: Record<string, unknown>;
  content_hash: string;
  semantic_interface_hash: string;
  status: 'ready' | 'invalid';
  findings: Record<string, unknown>[];
  created_at: string;
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
  map_blueprints: RpgMapBlueprintRevision[];
  revisions: RpgWorldRevision[];
  releases: RpgWorldRelease[];
  scenarios: RpgScenarioSummary[];
  scenario_revisions: Record<string, RpgScenarioRevision[]>;
  generation_runs: RpgWorldGenerationRun[];
}

export interface RpgWorldLaunchRepairResponse {
  ok: boolean;
  status: string;
  world: Record<string, unknown>;
  promotion: Record<string, unknown>;
  scenario_revision: RpgScenarioRevision;
  certification: Record<string, unknown>;
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

export interface RpgDeferredMaterializationResponse {
  ok: boolean;
  status: string;
  reused: boolean;
  materialization: Record<string, unknown>;
}

export interface RpgWorldGenerationMutationResponse {
  ok: boolean;
  run: RpgWorldGenerationRun;
  worker_started: boolean;
  scope?: Record<string, unknown>;
  retry_of_run_id?: string;
  continue_of_run_id?: string;
  diagnostic_id?: string;
  diagnostic_log?: string;
}

export class RpgWorldGenerationRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, retryable = false) {
    super(message);
    this.name = 'RpgWorldGenerationRequestError';
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const text = await response.text();
  if (!response.ok) {
    let detail: unknown = text;
    let code = 'world_generation_request_failed';
    let retryable = false;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown };
      const candidate = parsed.detail ?? parsed.error;
      detail = candidate;
      if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
        const error = candidate as Record<string, unknown>;
        if (typeof error.error === 'string') code = error.error;
        if (typeof error.retryable === 'boolean') retryable = error.retryable;
        if (typeof error.message === 'string') detail = error.message;
      }
    } catch {
      // Preserve the raw response body.
    }
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    throw new RpgWorldGenerationRequestError(
      response.status,
      code,
      `Omnix API request failed with status ${response.status}${message ? `: ${message}` : ''}`,
      retryable,
    );
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

  saveMapBlueprint(
    worldId: string,
    mapId: string,
    body: Record<string, unknown>,
  ): Promise<{ ok: boolean; map_blueprint: RpgMapBlueprintRevision }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/map-blueprints/${encodeURIComponent(mapId)}`,
      jsonInit(body),
    );
  },

  materializeMapBlueprints(
    worldId: string,
  ): Promise<{ ok: boolean; created: RpgMapBlueprintRevision[]; created_count: number }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/map-blueprints/materialize`,
      jsonInit({}),
    );
  },

  archiveWorld(worldId: string): Promise<{ ok: boolean; world: RpgWorldSummary; idempotent: boolean }> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/archive`, jsonInit({}));
  },

  restoreWorld(worldId: string): Promise<{ ok: boolean; world: RpgWorldSummary; idempotent: boolean }> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/restore`, jsonInit({}));
  },

  archiveScenario(
    scenarioId: string,
  ): Promise<{ ok: boolean; scenario: RpgScenarioSummary; idempotent: boolean }> {
    return request(`/api/rpg/scenarios/${encodeURIComponent(scenarioId)}/archive`, jsonInit({}));
  },

  restoreScenario(
    scenarioId: string,
  ): Promise<{ ok: boolean; scenario: RpgScenarioSummary; idempotent: boolean }> {
    return request(`/api/rpg/scenarios/${encodeURIComponent(scenarioId)}/restore`, jsonInit({}));
  },

  startGeneration(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<RpgWorldGenerationMutationResponse> {
    return request(`/api/rpg/worlds/${encodeURIComponent(worldId)}/generation`, jsonInit(body));
  },

  retryFailedGeneration(runId: string): Promise<RpgWorldGenerationMutationResponse> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/retry-failed`,
      jsonInit({}),
    );
  },

  continueGeneration(runId: string): Promise<RpgWorldGenerationMutationResponse> {
    return request(
      `/api/rpg/world-generation/${encodeURIComponent(runId)}/continue`,
      jsonInit({}),
    );
  },

  generationDiagnostics(): Promise<{
    ok: boolean;
    path: string;
    format: string;
    contains_generated_content: boolean;
  }> {
    return request('/api/rpg/world-generation/diagnostics');
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

  repairWorldForLaunch(
    worldId: string,
    body: Record<string, unknown>,
  ): Promise<RpgWorldLaunchRepairResponse> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/repair-for-launch`,
      jsonInit(body),
    );
  },

  prepareOpeningScenariosForLaunch(
    worldId: string,
  ): Promise<{
    ok: boolean;
    world_id: string;
    status?: 'generating' | 'ready' | 'review_required';
    generation_run_id?: string;
    prepared: Array<{ scenario_id: string; title: string }>;
  }> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/prepare-openings-for-launch`,
      jsonInit({}),
    );
  },

  materializeDeferredLocation(
    worldId: string,
    locationId: string,
    sourceWorldRevision: number,
  ): Promise<RpgDeferredMaterializationResponse> {
    return request(
      `/api/rpg/worlds/${encodeURIComponent(worldId)}/deferred-locations/${encodeURIComponent(locationId)}/materialize`,
      jsonInit({ source_world_revision: sourceWorldRevision }),
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
