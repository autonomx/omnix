import type { components, paths } from './generated/types';

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
