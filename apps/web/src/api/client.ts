import type { components, paths } from './generated/types';
import { withRpgGenesisContract } from './rpgGenesisPresentation';

export type GatewayApiPaths = paths;
export type GatewayApiPath = keyof GatewayApiPaths & string;
export type AssetLegacyImportDryRun = components['schemas']['AssetLegacyImportDryRun'];
export type AssetListResponse = components['schemas']['AssetListResponse'];
export type CancelJobRequest = components['schemas']['CancelJobRequest'];
export type ChatSession = components['schemas']['ChatSession'];
export type ChatSessionListResponse = components['schemas']['ChatSessionListResponse'];
export type CheckpointEnvelope = components['schemas']['CheckpointEnvelope'];
export type CreateChatSessionRequest = components['schemas']['CreateChatSessionRequest'];
export type CreateJobRequest = components['schemas']['CreateJobRequest'];
export type DiagnosticsPayload = components['schemas']['DiagnosticsPayload'];
export type JobListResponse = components['schemas']['JobListResponse'];
export type JobRecord = components['schemas']['JobRecord'];
export type ModelResidencyDiagnostics = components['schemas']['ModelResidencyDiagnostics'];
export type ModelResidencyRecord = components['schemas']['ModelResidencyRecord'];
export type PersistenceInventory = components['schemas']['PersistenceInventory'];
export type ProviderFacadePayload = components['schemas']['ProviderFacadePayload'];
export type ProviderModelRefreshRequest = components['schemas']['ProviderModelRefreshRequest'];
export type ReportListResponse = components['schemas']['ReportListResponse'];
export type SendChatMessageRequest = components['schemas']['SendChatMessageRequest'];
export type SendChatMessageResponse = components['schemas']['SendChatMessageResponse'];
export type SettingsPayload = components['schemas']['SettingsPayload'];
export type SettingsSaveResponse = components['schemas']['SettingsSaveResponse'];

export interface AssetContentResponse {
  asset: AssetListResponse['assets'][number];
  content: string;
  encoding: string;
  size_bytes: number;
  truncated: boolean;
}

export interface SaveStoryAssetRequest {
  title: string;
  content: string;
  premise?: string;
  provider_label?: string;
  word_count?: number;
  chapter_count?: number;
  source_job_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SavedStoryAssetResponse {
  asset: AssetListResponse['assets'][number];
  content: string;
}

export interface RpgPlayerOptions {
  name?: string;
  pronouns?: string;
  background?: string;
  build?: 'balanced_adventurer' | 'warrior' | 'ranger' | 'silver_tongue';
  portrait_seed?: number | null;
}

export interface RpgFeatureOptions {
  autosave?: boolean;
  validator?: boolean;
  background_soft_audit?: boolean;
  llm_narration?: boolean;
  image_generation?: boolean;
  tts?: boolean;
  stt?: boolean;
}

export type RpgCapability = 'combat' | 'recon' | 'influence' | 'technical' | 'survival' | 'knowledge' | 'support' | 'custom';
export type RpgPowerSource = 'mundane' | 'martial' | 'magic' | 'technology' | 'psionic' | 'divine' | 'occult' | 'mutation' | 'mythic' | 'social_power' | 'scrap' | 'custom';

export interface RpgNewGameRequest {
  campaign_template?: string;
  genre?: string | null;
  tone?: string;
  background?: string | null;
  starting_location?: string;
  player?: RpgPlayerOptions;
  primary_capability?: RpgCapability | null;
  secondary_capabilities?: RpgCapability[];
  power_source?: RpgPowerSource | null;
  generated_class_name?: string | null;
  generated_class_summary?: string | null;
  difficulty?: 'story' | 'normal' | 'harsh';
  world_activity?: 'quiet' | 'standard' | 'living_world';
  economy_pressure?: 'relaxed' | 'normal' | 'strict';
  combat_lethality?: 'safe' | 'normal' | 'deadly';
  companions_enabled?: boolean;
  permadeath?: boolean;
  seed?: number | null;
  initial_stats?: Record<string, number>;
  features?: RpgFeatureOptions;
  genesis?: Record<string, unknown>;
}

export interface RpgPresetSummary {
  preset_id: string;
  name: string;
  description: string;
  kind: string;
  level?: number;
  location?: string;
  clone_on_start?: boolean;
}

export interface RpgSessionListResponse {
  ok: boolean;
  sessions: Record<string, unknown>[];
  presets?: RpgPresetSummary[];
}

export interface RpgPresetListResponse {
  ok: boolean;
  presets: RpgPresetSummary[];
}

export interface RpgLaunchResponse {
  ok: boolean;
  session_id?: string;
  status?: string;
  session?: Record<string, unknown>;
  game?: Record<string, unknown>;
  error?: string;
}

export interface RpgSessionMutationResponse {
  ok: boolean;
  session_id?: string;
  session?: Record<string, unknown>;
  archived?: boolean;
  deleted?: string;
  error?: string;
}

export interface RpgLoadoutActionRequest {
  action: 'inspect' | 'use' | 'equip' | 'drop' | 'use_ability' | 'hotbar';
  item_name?: string;
  ability_name?: string;
  hotbar_slot?: string | number;
  target?: string;
}

export interface RpgLoadoutActionResponse extends RpgLaunchResponse {
  event?: Record<string, unknown>;
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export interface ApiRequestOptions {
  timeoutMessage?: string;
  timeoutMs?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`Omnix API request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export class ApiTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number, message?: string) {
    super(message ?? `Omnix API request timed out after ${Math.round(timeoutMs / 1000)}s.`);
    this.name = 'ApiTimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

export class OmnixApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '';
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  }

  async get<T>(path: `/api/${string}`): Promise<T> {
    return this.request<T>(path, { method: 'GET' });
  }

  async post<TRequest, TResponse>(path: `/api/${string}`, body: TRequest, options: ApiRequestOptions = {}): Promise<TResponse> {
    return this.request<TResponse>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }, options);
  }

  async listChatSessions(): Promise<ChatSessionListResponse> {
    return this.get<ChatSessionListResponse>('/api/chat/sessions');
  }

  async createChatSession(request: CreateChatSessionRequest): Promise<ChatSession> {
    return this.post<CreateChatSessionRequest, ChatSession>('/api/chat/sessions', request);
  }

  async getChatSession(sessionId: string): Promise<ChatSession> {
    return this.get<ChatSession>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
  }

  async sendChatMessage(sessionId: string, request: SendChatMessageRequest): Promise<SendChatMessageResponse> {
    return this.post<SendChatMessageRequest, SendChatMessageResponse>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
      request,
    );
  }

  async listProviders(): Promise<ProviderFacadePayload> {
    return this.get<ProviderFacadePayload>('/api/providers');
  }

  async listModels(): Promise<ProviderFacadePayload> {
    return this.get<ProviderFacadePayload>('/api/models');
  }

  async refreshProviders(request: ProviderModelRefreshRequest = { scope: 'all', priority: 0 }): Promise<JobRecord> {
    return this.post<ProviderModelRefreshRequest, JobRecord>('/api/providers/refresh', request);
  }

  async refreshModels(request: ProviderModelRefreshRequest = { scope: 'models', priority: 0 }): Promise<JobRecord> {
    return this.post<ProviderModelRefreshRequest, JobRecord>('/api/models/refresh', request);
  }

  async getModelResidency(): Promise<ModelResidencyDiagnostics> {
    return this.get<ModelResidencyDiagnostics>('/api/model-residency');
  }

  async reportModelResidency(request: ModelResidencyRecord): Promise<ModelResidencyDiagnostics> {
    return this.post<ModelResidencyRecord, ModelResidencyDiagnostics>('/api/model-residency', request);
  }

  async deleteModelResidency(modelId: string): Promise<ModelResidencyDiagnostics> {
    return this.request<ModelResidencyDiagnostics>(`/api/model-residency/${encodeURIComponent(modelId)}`, {
      method: 'DELETE',
    });
  }

  async listJobs(): Promise<JobListResponse> {
    return this.get<JobListResponse>('/api/jobs');
  }

  async createJob(request: CreateJobRequest, options: ApiRequestOptions = {}): Promise<JobRecord> {
    return this.post<CreateJobRequest, JobRecord>('/api/jobs', request, options);
  }

  async cancelJob(jobId: string, reason: string): Promise<JobRecord> {
    return this.post<CancelJobRequest, JobRecord>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { reason });
  }

  async listAssets(): Promise<AssetListResponse> {
    return this.get<AssetListResponse>('/api/assets');
  }

  async getAssetContent(assetId: string): Promise<AssetContentResponse> {
    return this.get<AssetContentResponse>(`/api/assets/${encodeURIComponent(assetId)}/content`);
  }

  async saveStoryAsset(request: SaveStoryAssetRequest): Promise<SavedStoryAssetResponse> {
    return this.post<SaveStoryAssetRequest, SavedStoryAssetResponse>('/api/assets/story', request);
  }

  async previewLegacyNonImageAssetImport(): Promise<AssetLegacyImportDryRun> {
    return this.request<AssetLegacyImportDryRun>('/api/assets/migrations/legacy-non-image/dry-run', {
      method: 'POST',
    });
  }

  async listReports(): Promise<ReportListResponse> {
    return this.get<ReportListResponse>('/api/reports');
  }

  async getReplayPersistenceInventory(): Promise<PersistenceInventory> {
    return this.get<PersistenceInventory>('/api/replay/persistence/inventory');
  }

  async listRpgPresets(): Promise<RpgPresetListResponse> {
    try {
      return await this.get<RpgPresetListResponse>('/api/rpg/presets');
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      const compatibility = await this.post<Record<string, never>, RpgSessionListResponse>('/api/rpg/session/list', {});
      return { ok: compatibility.ok, presets: compatibility.presets ?? [] };
    }
  }

  async listRpgSessions(): Promise<RpgSessionListResponse> {
    try {
      const [sessions, presets] = await Promise.all([
        this.get<RpgSessionListResponse>('/api/rpg/sessions'),
        this.listRpgPresets(),
      ]);
      return { ...sessions, presets: presets.presets };
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, never>, RpgSessionListResponse>('/api/rpg/session/list', {});
    }
  }

  async createRpgNewGame(request: RpgNewGameRequest = {}): Promise<RpgLaunchResponse> {
    const genesisRequest = withRpgGenesisContract(request);
    try {
      return await this.post<RpgNewGameRequest, RpgLaunchResponse>('/api/rpg/new-game', genesisRequest);
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
        action: 'new_game',
        request: genesisRequest,
      });
    }
  }

  async startRpgPreset(presetId: string): Promise<RpgLaunchResponse> {
    try {
      return await this.post<Record<string, never>, RpgLaunchResponse>(`/api/rpg/presets/${encodeURIComponent(presetId)}/start`, {});
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
        action: 'start_preset',
        preset_id: presetId,
      });
    }
  }

  async continueRpgSession(sessionId: string): Promise<RpgLaunchResponse> {
    try {
      return await this.post<Record<string, never>, RpgLaunchResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/continue`, {});
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
        action: 'continue',
        session_id: sessionId,
      });
    }
  }

  async renameRpgSession(sessionId: string, name: string): Promise<RpgSessionMutationResponse> {
    try {
      return await this.post<{ name: string }, RpgSessionMutationResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/rename`, { name });
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, unknown>, RpgSessionMutationResponse>('/api/rpg/session/get', {
        action: 'rename',
        session_id: sessionId,
        name,
      });
    }
  }

  async deleteRpgSession(sessionId: string): Promise<RpgSessionMutationResponse> {
    try {
      return await this.post<Record<string, never>, RpgSessionMutationResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/delete`, {});
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, unknown>, RpgSessionMutationResponse>('/api/rpg/session/get', {
        action: 'delete',
        session_id: sessionId,
      });
    }
  }

  async applyRpgLoadoutAction(sessionId: string, request: RpgLoadoutActionRequest): Promise<RpgLoadoutActionResponse> {
    try {
      return await this.post<RpgLoadoutActionRequest, RpgLoadoutActionResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/loadout-action`, request);
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, unknown>, RpgLoadoutActionResponse>('/api/rpg/session/get', {
        action: 'loadout_action',
        session_id: sessionId,
        loadout: request,
      });
    }
  }

  async createReplayCheckpoint(request: Record<string, unknown>): Promise<CheckpointEnvelope> {
    return this.post<Record<string, unknown>, CheckpointEnvelope>('/api/replay/checkpoints', request);
  }

  async getSettings(): Promise<SettingsPayload> {
    return this.get<SettingsPayload>('/api/settings');
  }

  async saveSettings(request: Record<string, unknown>): Promise<SettingsSaveResponse> {
    return this.post<Record<string, unknown>, SettingsSaveResponse>('/api/settings', request);
  }

  async getDiagnostics(): Promise<DiagnosticsPayload> {
    return this.get<DiagnosticsPayload>('/api/diagnostics');
  }

  private isNotFound(error: unknown): boolean {
    return error instanceof ApiError && error.status === 404;
  }

  private async request<T>(path: `/api/${string}`, init: RequestInit, options: ApiRequestOptions = {}): Promise<T> {
    let didTimeout = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const controller = options.timeoutMs ? new AbortController() : undefined;

    if (controller && options.timeoutMs) {
      timeoutId = setTimeout(() => {
        didTimeout = true;
        controller.abort();
      }, options.timeoutMs);
    }

    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller?.signal ?? init.signal,
      });
      const text = await response.text();

      if (!response.ok) {
        throw new ApiError(response.status, text);
      }

      if (!text) {
        return undefined as T;
      }

      return JSON.parse(text) as T;
    } catch (error) {
      if (didTimeout && options.timeoutMs) {
        throw new ApiTimeoutError(options.timeoutMs, options.timeoutMessage);
      }
      throw error;
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
  }
}

export const omnixApiClient = new OmnixApiClient();
