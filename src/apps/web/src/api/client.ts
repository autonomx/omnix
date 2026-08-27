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
export type CodexAuthStatus = components['schemas']['CodexAuthStatus'];
type GeneratedCreateChatSessionRequest = components['schemas']['CreateChatSessionRequest'];
export type CreateChatSessionRequest = Partial<GeneratedCreateChatSessionRequest>;
export type CreateJobRequest = components['schemas']['CreateJobRequest'];
export type DiagnosticsPayload = components['schemas']['DiagnosticsPayload'];
export type JobListResponse = components['schemas']['JobListResponse'];
export type ListJobsOptions = { limit?: number; full?: boolean };
export type JobRecord = components['schemas']['JobRecord'];
export type ModelResidencyDiagnostics = components['schemas']['ModelResidencyDiagnostics'];
export type ModelResidencyRecord = components['schemas']['ModelResidencyRecord'];
export type PersistenceInventory = components['schemas']['PersistenceInventory'];
export type ProviderFacadePayload = components['schemas']['ProviderFacadePayload'];
export type ProviderModelRefreshRequest = components['schemas']['ProviderModelRefreshRequest'];
export type ReportListResponse = components['schemas']['ReportListResponse'];
type GeneratedSendChatMessageRequest = components['schemas']['SendChatMessageRequest'];
export type SendChatMessageRequest = Pick<GeneratedSendChatMessageRequest, 'content'>
  & Partial<Omit<GeneratedSendChatMessageRequest, 'content'>>;
export type SendChatMessageResponse = components['schemas']['SendChatMessageResponse'];
export type SettingsPayload = components['schemas']['SettingsPayload'];
export type SettingsSaveResponse = components['schemas']['SettingsSaveResponse'];

export interface DeleteChatSessionResponse {
  ok: boolean;
  session_id: string;
}

export interface DeepResearchPlanUpdateRequest {
  max_pages: number;
}

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

export interface RpgLaunchRequestTraceEvent {
  endpoint: string;
  method: string;
  status: 'started' | 'completed' | 'failed' | 'fallback';
  elapsed_ms?: number;
  http_status?: number;
  error?: string;
}

export interface RpgLaunchRequestTrace {
  active_endpoint?: string;
  final_endpoint?: string;
  elapsed_ms?: number;
  events: RpgLaunchRequestTraceEvent[];
}

export interface RpgLaunchResponse {
  ok: boolean;
  session_id?: string;
  status?: string;
  session?: Record<string, unknown>;
  game?: Record<string, unknown>;
  environment_snapshot?: Record<string, unknown>;
  creation_request_trace?: RpgLaunchRequestTrace;
  creation_server_trace?: Record<string, unknown>;
  creation_job?: Record<string, unknown>;
  creation_progress?: Record<string, unknown>;
  error?: string;
}

interface RpgForegroundTurnResponse extends RpgLaunchResponse {
  command?: string;
  response?: string;
  content?: string;
  result?: Record<string, unknown>;
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
    let detail = '';
    try {
      const parsed = JSON.parse(body) as { detail?: unknown; error?: unknown };
      const candidate = parsed.detail ?? parsed.error;
      detail = typeof candidate === 'string'
        ? candidate
        : candidate && typeof candidate === 'object'
          ? JSON.stringify(candidate)
          : '';
    } catch {
      detail = body.trim();
    }
    super(`Omnix API request failed with status ${status}${detail ? `: ${detail}` : ''}`);
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

function nowMs(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}

function logRpgLaunchTrace(message: string, detail?: unknown): void {
  if (typeof console === 'undefined') {
    return;
  }
  console.info(`[RPG][new-game][client] ${message}`, detail ?? '');
}

function warnRpgLaunchTrace(message: string, detail?: unknown): void {
  if (typeof console === 'undefined') {
    return;
  }
  console.warn(`[RPG][new-game][client] ${message}`, detail ?? '');
}

function errorLabel(error: unknown): string {
  if (error instanceof ApiError) {
    return `HTTP ${error.status}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'request_failed';
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
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
    return this.request<TResponse>(
      path,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
      options
    );
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

  async deleteChatSession(sessionId: string): Promise<DeleteChatSessionResponse> {
    return this.request<DeleteChatSessionResponse>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  }

  async sendChatMessage(sessionId: string, request: SendChatMessageRequest): Promise<SendChatMessageResponse> {
    return this.post<SendChatMessageRequest, SendChatMessageResponse>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, request);
  }

  async updateDeepResearchPlan(jobId: string, request: DeepResearchPlanUpdateRequest): Promise<JobRecord> {
    return this.request<JobRecord>(
      `/api/assistant/context/research/jobs/${encodeURIComponent(jobId)}/plan`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      },
    );
  }

  async startDeepResearchPlan(jobId: string): Promise<JobRecord> {
    return this.post<Record<string, never>, JobRecord>(
      `/api/assistant/context/research/jobs/${encodeURIComponent(jobId)}/start`,
      {},
    );
  }

  async listProviders(): Promise<ProviderFacadePayload> {
    return this.get<ProviderFacadePayload>('/api/providers');
  }

  async listModels(): Promise<ProviderFacadePayload> {
    return this.get<ProviderFacadePayload>('/api/models');
  }

  async getCodexAuthStatus(): Promise<CodexAuthStatus> {
    return this.get<CodexAuthStatus>('/api/providers/chatgpt-codex/auth');
  }

  async startCodexLogin(): Promise<CodexAuthStatus> {
    return this.post<Record<string, never>, CodexAuthStatus>('/api/providers/chatgpt-codex/login', {});
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
    return this.request<ModelResidencyDiagnostics>(`/api/model-residency/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
  }

  async listJobs(options: ListJobsOptions = {}): Promise<JobListResponse> {
    const query = new URLSearchParams();
    if (options.limit !== undefined) query.set('limit', String(options.limit));
    if (options.full !== undefined) query.set('full', String(options.full));
    const suffix = query.size ? `?${query.toString()}` : '';
    return this.get<JobListResponse>(`/api/jobs${suffix}`);
  }

  async createJob(request: CreateJobRequest, options: ApiRequestOptions = {}): Promise<JobRecord> {
    const foregroundTurn = await this.createForegroundRpgTurnJob(request);
    if (foregroundTurn) {
      return foregroundTurn;
    }
    return this.post<CreateJobRequest, JobRecord>('/api/jobs', request, options);
  }

  async getJob(jobId: string): Promise<JobRecord> {
    return this.get<JobRecord>(`/api/jobs/${encodeURIComponent(jobId)}`);
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

  async deleteVoiceAsset(assetId: string): Promise<{ ok: boolean; asset_id: string; deleted: boolean; file_deleted: boolean }> {
    return this.request(`/api/voice-cloning/assets/${encodeURIComponent(assetId)}`, { method: 'DELETE' });
  }

  async saveStoryAsset(request: SaveStoryAssetRequest): Promise<SavedStoryAssetResponse> {
    return this.post<SaveStoryAssetRequest, SavedStoryAssetResponse>('/api/assets/story', request);
  }

  async previewLegacyNonImageAssetImport(): Promise<AssetLegacyImportDryRun> {
    return this.request<AssetLegacyImportDryRun>('/api/assets/migrations/legacy-non-image/dry-run', { method: 'POST' });
  }

  async listReports(): Promise<ReportListResponse> {
    return this.get<ReportListResponse>('/api/reports');
  }

  async getReplayPersistenceInventory(): Promise<PersistenceInventory> {
    try {
      return await this.get<PersistenceInventory>('/api/replay/persistence/inventory');
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return (await this.listRpgSessions()) as unknown as PersistenceInventory;
    }
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
      const [sessions, presets] = await Promise.all([this.get<RpgSessionListResponse>('/api/rpg/sessions'), this.listRpgPresets()]);
      return { ...sessions, presets: presets.presets };
    } catch (error) {
      if (!this.isNotFound(error)) {
        throw error;
      }
      return this.post<Record<string, never>, RpgSessionListResponse>('/api/rpg/session/list', {});
    }
  }

  async listRpgSessionSummaries(): Promise<RpgSessionListResponse> {
    return this.get<RpgSessionListResponse>('/api/rpg/sessions');
  }

  async getRpgSession(sessionId: string): Promise<RpgLaunchResponse> {
    return this.get<RpgLaunchResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}`);
  }

  async createRpgNewGame(request: RpgNewGameRequest = {}): Promise<RpgLaunchResponse> {
    const genesisRequest = withRpgGenesisContract(request);
    const traceStartedAt = nowMs();
    const events: RpgLaunchRequestTraceEvent[] = [{ endpoint: '/api/rpg/new-game', method: 'POST', status: 'started' }];
    logRpgLaunchTrace('starting POST /api/rpg/new-game');
    try {
      const startedAt = nowMs();
      const result = await this.post<RpgNewGameRequest, RpgLaunchResponse>('/api/rpg/new-game', genesisRequest);
      const elapsed = Math.round(nowMs() - startedAt);
      events.push({ endpoint: '/api/rpg/new-game', method: 'POST', status: 'completed', elapsed_ms: elapsed });
      const tracedResult = {
        ...result,
        creation_request_trace: {
          active_endpoint: '/api/rpg/new-game',
          final_endpoint: '/api/rpg/new-game',
          elapsed_ms: Math.round(nowMs() - traceStartedAt),
          events,
        },
      };
      logRpgLaunchTrace('completed POST /api/rpg/new-game', tracedResult.creation_request_trace);
      if (tracedResult.creation_server_trace) {
        logRpgLaunchTrace('server trace', tracedResult.creation_server_trace);
      }
      return tracedResult;
    } catch (error) {
      const primaryElapsed = Math.round(nowMs() - traceStartedAt);
      events.push({
        endpoint: '/api/rpg/new-game',
        method: 'POST',
        status: 'failed',
        elapsed_ms: primaryElapsed,
        http_status: error instanceof ApiError ? error.status : undefined,
        error: errorLabel(error),
      });
      warnRpgLaunchTrace('primary POST /api/rpg/new-game failed', events[events.length - 1]);
      if (!this.isNotFound(error)) {
        throw error;
      }
      events.push({ endpoint: '/api/rpg/session/get', method: 'POST', status: 'fallback' });
      logRpgLaunchTrace('falling back to POST /api/rpg/session/get');
      const fallbackStartedAt = nowMs();
      const result = await this.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
        action: 'new_game',
        request: genesisRequest,
      });
      events.push({ endpoint: '/api/rpg/session/get', method: 'POST', status: 'completed', elapsed_ms: Math.round(nowMs() - fallbackStartedAt) });
      const tracedResult = {
        ...result,
        creation_request_trace: {
          active_endpoint: '/api/rpg/session/get',
          final_endpoint: '/api/rpg/session/get',
          elapsed_ms: Math.round(nowMs() - traceStartedAt),
          events,
        },
      };
      logRpgLaunchTrace('completed POST /api/rpg/session/get', tracedResult.creation_request_trace);
      if (tracedResult.creation_server_trace) {
        logRpgLaunchTrace('server trace', tracedResult.creation_server_trace);
      }
      return tracedResult;
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

  private async createForegroundRpgTurnJob(request: CreateJobRequest): Promise<JobRecord | null> {
    const requestRecord = request as Record<string, unknown>;
    if (requestRecord.module !== 'rpg' || requestRecord.type !== 'rpg.turn') {
      return null;
    }

    const inputRef = asRecord(requestRecord.input_ref);
    const inputPayload = asRecord(requestRecord.input_payload);
    const sessionId = stringValue(inputRef.session_id);
    const command = stringValue(inputPayload.command);
    if (!sessionId || !command) {
      return null;
    }

    const clientSubmitMs = Date.now();
    const clientSubmitAt = new Date(clientSubmitMs).toISOString();
    let result: RpgForegroundTurnResponse;
    try {
      result = await this.post<{ command: string }, RpgForegroundTurnResponse>(
        `/api/rpg/sessions/${encodeURIComponent(sessionId)}/turn`,
        { command },
      );
    } catch (error) {
      if (this.isNotFound(error)) {
        return null;
      }
      throw error;
    }
    const seenMs = Date.now();
    const seenAt = new Date(seenMs).toISOString();
    const content = result.content || result.response || '';
    const clientVisibleTimestamps = {
      client_submit_at: clientSubmitAt,
      server_job_created_at: result.creation_server_trace?.server_job_created_at ?? result.creation_server_trace?.created_at ?? null,
      server_job_started_at: result.creation_server_trace?.server_job_started_at ?? result.creation_server_trace?.started_at ?? null,
      server_job_completed_at: result.creation_server_trace?.server_job_completed_at ?? result.creation_server_trace?.completed_at ?? null,
      server_response_persisted_at: result.creation_server_trace?.server_response_persisted_at ?? result.creation_server_trace?.response_persisted_at ?? null,
      sse_or_poll_seen_at: seenAt,
      ui_render_started_at: null,
      ui_render_completed_at: null,
      client_turn_request_ms: seenMs - clientSubmitMs,
    };
    return {
      id: `foreground:rpg.turn:${clientSubmitMs}`,
      module: 'rpg',
      type: 'rpg.turn',
      resource_class: requestRecord.resource_class ?? 'gpu:llm',
      priority: typeof requestRecord.priority === 'number' ? requestRecord.priority : 0,
      status: 'completed',
      input_ref: inputRef,
      input_payload: {
        ...inputPayload,
        client_visible_timestamps: clientVisibleTimestamps,
      },
      output_refs: [
        {
          type: 'rpg_turn_response',
          module: 'rpg',
          title: command.slice(0, 80) || 'RPG turn',
          content,
          result,
          client_visible_timestamps: clientVisibleTimestamps,
        },
      ],
      logs: [
        {
          level: 'info',
          message: 'RPG turn applied through the foreground session route.',
          content,
          client_visible_timestamps: clientVisibleTimestamps,
        },
      ],
      stages: [],
      error: null,
      created_at: clientSubmitAt,
      updated_at: seenAt,
    } as unknown as JobRecord;
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
