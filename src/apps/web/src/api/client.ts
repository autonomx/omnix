import type { components, paths } from './generated/types';
import { ApiError, ApiTimeoutError } from './errors';
import { createGatewayClient, requestTimeout, unwrap, type GatewayClient } from './http';
import { withRpgGenesisContract } from '../features/rpg/api/rpgGenesisPresentation';
import { pipelineFetch } from './fetchPipeline';

export { ApiError, ApiTimeoutError } from './errors';

export type GatewayApiPaths = paths;
export type GatewayApiPath = keyof GatewayApiPaths & string;
export type AssetLegacyImportDryRun = components['schemas']['PublicAssetLegacyImportDryRun'];
export type AssetListResponse = components['schemas']['PublicAssetListResponse'];

export type CancelJobRequest = components['schemas']['CancelJobRequest'];
export type ChatSession = components['schemas']['ChatSession'];
export type ChatSessionListResponse = components['schemas']['ChatSessionListResponse'];
export type ChatSessionAttachments = Record<string, string[]>;
export type CheckpointEnvelope = components['schemas']['CheckpointEnvelope'];
export type CodexAuthStatus = components['schemas']['CodexAuthStatus'];
export type CreateChatSessionRequest = components['schemas']['CreateChatSessionRequest'];
export type CreateJobRequest = components['schemas']['CreateJobRequest'];
export type DiagnosticsPayload = components['schemas']['DiagnosticsPayload'];
export type JobListResponse = components['schemas']['JobListResponse'];
export type ListJobsOptions = { limit?: number; full?: boolean; cursor?: string | null };
type AssetListQuery = NonNullable<paths['/api/assets']['get']['parameters']['query']>;
export type ListAssetsOptions = { type?: AssetListQuery['type']; module?: string; limit?: number; cursor?: string | null };
export type JobRecord = components['schemas']['JobRecord'];
export type ModelResidencyDiagnostics = components['schemas']['ModelResidencyDiagnostics'];
export type ModelResidencyRecord = components['schemas']['ModelResidencyRecord'];
export type PersistenceInventory = components['schemas']['PersistenceInventory'];
export type ProviderFacadePayload = components['schemas']['ProviderFacadePayload'];
export type ProviderModelRefreshRequest = components['schemas']['ProviderModelRefreshRequest'];
export type ReportListResponse = components['schemas']['ReportListResponse'];
export type SendChatMessageRequest = components['schemas']['SendChatMessageRequest'];
export type CodingApprovalPolicy = NonNullable<SendChatMessageRequest['coding_approval_policy']>;
export type SendChatMessageResponse = components['schemas']['SendChatMessageResponse'];
export type AssistantContextChatRequest = components['schemas']['AssistantContextChatRequest'];
export type SettingsPayload = components['schemas']['SettingsPayload'];
export type SettingsSaveResponse = components['schemas']['SettingsSaveResponse'];

export type AgentRunSnapshot = components['schemas']['AgentRunSnapshot'];
export type AgentRunEvent = components['schemas']['AgentEvent'];
export type AgentArtifact = components['schemas']['AgentArtifact'];
export type AgentApproval = components['schemas']['AgentApproval'];
export type AgentTaskRevision = components['schemas']['TaskRevision'];
export type AgentEvidenceReceipt = components['schemas']['EvidenceReceipt'];
export type AgentEvidenceSet = components['schemas']['EvidenceSet'];
export type TaskGraphRunSnapshot = components['schemas']['TaskGraphRunSnapshot'];
export type TaskGraphEvent = components['schemas']['TaskGraphEvent'];
export type DeleteChatSessionResponse = components['schemas']['DeleteChatSessionResponse'];
export type DeepResearchPlanUpdateRequest = components['schemas']['DeepResearchPlanUpdateRequest'];
export type AssetContentResponse = components['schemas']['AssetContentResponse'];
export type SaveStoryAssetRequest = components['schemas']['SaveStoryAssetRequest'];
export type SavedStoryAssetResponse = components['schemas']['SavedStoryAssetResponse'];

/** `/api/workflow-runs/{run_id}` returns an untyped object; the fields the UI reads. */
export interface WorkflowRunSnapshot {
  run_id: string;
  workflow_id: string;
  workflow_version: number;
  status: string;
  current_step_id?: string | null;
  input_payload: Record<string, unknown>;
  revision: number;
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

const ASSET_PAGE_SIZE = 200;
// Stops a runaway loop; 200 pages hold 40,000 assets.
const MAX_ASSET_PAGES = 200;

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

  private readonly api: GatewayClient;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '';
    this.fetchImpl = options.fetchImpl ?? ((input, init) => pipelineFetch(input, init));
    this.api = createGatewayClient({ baseUrl: options.baseUrl || undefined, fetchImpl: this.fetchImpl });
  }

  /** Sends one typed call, optionally with a timeout, and returns its body (WP-9.3). */
  private async call<T>(
    send: (signal?: AbortSignal) => Promise<{ data?: T; error?: unknown; response: Response }>,
    options: ApiRequestOptions = {},
  ): Promise<T> {
    if (!options.timeoutMs) return unwrap(send());
    const timeout = requestTimeout(options.timeoutMs, options.timeoutMessage);
    try {
      return await unwrap(send(timeout.signal));
    } catch (error) {
      throw timeout.timedOut(error);
    } finally {
      timeout.clear();
    }
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
    const sessions: ChatSessionListResponse['sessions'] = [];
    const cursors = new Set<string>();
    let cursor: string | null = null;
    do {
      const query: { limit?: number; cursor?: string } = cursor ? { limit: 100, cursor } : {};
      const page: ChatSessionListResponse = await this.call(() => this.api.GET('/api/chat/sessions', { params: { query } }));
      sessions.push(...page.sessions);
      cursor = page.next_cursor ?? null;
      if (cursor && cursors.has(cursor)) {
        throw new Error('Chat session pagination did not advance');
      }
      if (cursor) cursors.add(cursor);
    } while (cursor);
    return { sessions, next_cursor: null };
  }

  async createChatSession(request: CreateChatSessionRequest): Promise<ChatSession> {
    return this.call(() => this.api.POST('/api/chat/sessions', { body: request }));
  }

  async getChatSession(sessionId: string, options?: { includeAttachments?: boolean }): Promise<ChatSession> {
    const query = options?.includeAttachments === false ? { include_attachments: false } : {};
    return this.call(() => this.api.GET('/api/chat/sessions/{session_id}', { params: { path: { session_id: sessionId }, query } }));
  }

  async getChatSessionAttachments(sessionId: string): Promise<ChatSessionAttachments> {
    return this.call(() => this.api.GET('/api/chat/sessions/{session_id}/attachments', { params: { path: { session_id: sessionId } } }));
  }

  async deleteChatSession(sessionId: string): Promise<DeleteChatSessionResponse> {
    return this.call(() => this.api.DELETE('/api/chat/sessions/{session_id}', { params: { path: { session_id: sessionId } } }));
  }

  async sendChatMessage(sessionId: string, request: SendChatMessageRequest): Promise<SendChatMessageResponse> {
    return this.call(
      (signal) => this.api.POST('/api/chat/sessions/{session_id}/messages', { params: { path: { session_id: sessionId } }, body: request, signal }),
      { timeoutMs: 15_000, timeoutMessage: 'Chat request was not accepted by the gateway within 15s.' },
    );
  }

  /** Sends a chat message with the context tools' fields (research, agent mode, desktop, local folder). */
  async sendAssistantContextChatMessage(sessionId: string, request: AssistantContextChatRequest): Promise<SendChatMessageResponse> {
    return this.call(
      (signal) => this.api.POST('/api/assistant/context/chat/sessions/{session_id}/messages', { params: { path: { session_id: sessionId } }, body: request, signal }),
      { timeoutMs: 15_000, timeoutMessage: 'Chat request was not accepted by the gateway within 15s.' },
    );
  }

  async getAgentRun(runId: string): Promise<AgentRunSnapshot> {
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}', { params: { path: { run_id: runId } } }));
  }

  async listAgentRunEvents(runId: string, afterSequence = 0): Promise<AgentRunEvent[]> {
    const query = afterSequence > 0 ? { after_sequence: afterSequence } : {};
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}/events', { params: { path: { run_id: runId }, query } }));
  }

  async listAgentArtifacts(runId: string): Promise<AgentArtifact[]> {
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}/artifacts', { params: { path: { run_id: runId } } }));
  }

  async listAgentTaskRevisions(runId: string): Promise<AgentTaskRevision[]> {
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}/task-revisions', { params: { path: { run_id: runId } } }));
  }

  async listAgentEvidenceReceipts(runId: string): Promise<AgentEvidenceReceipt[]> {
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}/evidence/receipts', { params: { path: { run_id: runId } } }));
  }

  async getAgentEvidenceSet(runId: string): Promise<AgentEvidenceSet> {
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}/evidence', { params: { path: { run_id: runId } } }));
  }

  async commandAgentRun(
    runId: string,
    commandType: 'steer' | 'pause' | 'resume' | 'cancel' | 'approve' | 'reject',
    payload: Record<string, unknown> = {},
  ): Promise<AgentRunSnapshot> {
    return this.call(() => this.api.POST('/api/agent-runs/{run_id}/commands', {
      params: { path: { run_id: runId } },
      body: { command_type: commandType, payload },
    }));
  }

  async listAgentApprovals(runId: string, state?: string): Promise<AgentApproval[]> {
    const query = state ? { state } : {};
    return this.call(() => this.api.GET('/api/agent-runs/{run_id}/approvals', { params: { path: { run_id: runId }, query } }));
  }

  async getTaskGraphRun(runId: string): Promise<TaskGraphRunSnapshot> {
    return this.call(() => this.api.GET('/api/task-graph-runs/{run_id}', { params: { path: { run_id: runId } } }));
  }

  async listTaskGraphEvents(runId: string, afterSequence = 0): Promise<TaskGraphEvent[]> {
    const query = afterSequence > 0 ? { after_sequence: afterSequence } : {};
    return this.call(() => this.api.GET('/api/task-graph-runs/{run_id}/events', { params: { path: { run_id: runId }, query } }));
  }

  async commandTaskGraphRun(
    runId: string,
    command: 'advance' | 'recover' | 'cancel' | 'approve' | 'reject',
    nodeId?: string,
    approvalId?: string,
  ): Promise<TaskGraphRunSnapshot> {
    return this.call(() => this.api.POST('/api/task-graph-runs/{run_id}/commands', {
      params: { path: { run_id: runId } },
      body: {
        command,
        ...(nodeId ? { node_id: nodeId } : {}),
        ...(approvalId ? { approval_id: approvalId } : {}),
      },
    }));
  }

  async getWorkflowRun(runId: string): Promise<WorkflowRunSnapshot> {
    const run = await this.call(() => this.api.GET('/api/workflow-runs/{run_id}', { params: { path: { run_id: runId } } }));
    return run as unknown as WorkflowRunSnapshot;
  }

  async commandWorkflowRun(
    runId: string,
    command: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject',
    stepId?: string,
  ): Promise<WorkflowRunSnapshot> {
    const run = await this.call(() => this.api.POST('/api/workflow-runs/{run_id}/commands', {
      params: { path: { run_id: runId } },
      body: { command, ...(stepId ? { step_id: stepId } : {}) },
    }));
    return run as unknown as WorkflowRunSnapshot;
  }

  async updateDeepResearchPlan(jobId: string, request: DeepResearchPlanUpdateRequest): Promise<JobRecord> {
    return this.call(() => this.api.PATCH('/api/assistant/context/research/jobs/{job_id}/plan', { params: { path: { job_id: jobId } }, body: request }));
  }

  async startDeepResearchPlan(jobId: string): Promise<JobRecord> {
    return this.call(() => this.api.POST('/api/assistant/context/research/jobs/{job_id}/start', { params: { path: { job_id: jobId } } }));
  }

  async listProviders(): Promise<ProviderFacadePayload> {
    return this.call(() => this.api.GET('/api/providers'));
  }

  async listModels(): Promise<ProviderFacadePayload> {
    return this.call(() => this.api.GET('/api/models'));
  }

  async getCodexAuthStatus(): Promise<CodexAuthStatus> {
    return this.call(() => this.api.GET('/api/providers/chatgpt-codex/auth'));
  }

  async startCodexLogin(): Promise<CodexAuthStatus> {
    return this.call(() => this.api.POST('/api/providers/chatgpt-codex/login'));
  }

  async refreshProviders(request: ProviderModelRefreshRequest = { scope: 'all', priority: 0 }): Promise<JobRecord> {
    return this.call(() => this.api.POST('/api/providers/refresh', { body: request }));
  }

  async refreshModels(request: ProviderModelRefreshRequest = { scope: 'models', priority: 0 }): Promise<JobRecord> {
    return this.call(() => this.api.POST('/api/models/refresh', { body: request }));
  }

  // openapi-fetch reads the policy's model pairs as string[][]; the schema says pairs.
  async getModelResidency(): Promise<ModelResidencyDiagnostics> {
    return this.call(() => this.api.GET('/api/model-residency')) as Promise<ModelResidencyDiagnostics>;
  }

  async reportModelResidency(request: ModelResidencyRecord): Promise<ModelResidencyDiagnostics> {
    return this.call(() => this.api.POST('/api/model-residency', { body: request })) as Promise<ModelResidencyDiagnostics>;
  }

  async deleteModelResidency(modelId: string): Promise<ModelResidencyDiagnostics> {
    return this.call(() => this.api.DELETE('/api/model-residency/{model_id}', { params: { path: { model_id: modelId } } })) as Promise<ModelResidencyDiagnostics>;
  }

  async listJobs(options: ListJobsOptions = {}): Promise<JobListResponse> {
    const query: { limit?: number; full?: boolean; cursor?: string } = {};
    if (options.limit !== undefined) query.limit = options.limit;
    if (options.full !== undefined) query.full = options.full;
    if (options.cursor) query.cursor = options.cursor;
    return this.call(() => this.api.GET('/api/jobs', { params: { query } }));
  }

  /** Voice Studio's bounded job history: recent voice and voice-cloning jobs only. */
  async listVoiceJobSummaries(limit = 40): Promise<JobListResponse> {
    return this.call(() => this.api.GET('/api/jobs/voice-summaries', { params: { query: { limit } } }));
  }

  async createJob(request: CreateJobRequest, options: ApiRequestOptions = {}): Promise<JobRecord> {
    const foregroundTurn = await this.createForegroundRpgTurnJob(request);
    if (foregroundTurn) {
      return foregroundTurn;
    }
    return this.call((signal) => this.api.POST('/api/jobs', { body: request, signal }), options);
  }

  async getJob(jobId: string): Promise<JobRecord> {
    return this.call(() => this.api.GET('/api/jobs/{job_id}', { params: { path: { job_id: jobId } } }));
  }

  async cancelJob(jobId: string, reason: string): Promise<JobRecord> {
    return this.call(() => this.api.POST('/api/jobs/{job_id}/cancel', { params: { path: { job_id: jobId } }, body: { reason } }));
  }

  /**
   * Every asset matching the filter, newest first. The gateway returns pages
   * of at most 200; this follows `next_cursor` until the last page.
   */
  async listAssets(filter: Pick<ListAssetsOptions, 'type' | 'module'> = {}): Promise<AssetListResponse> {
    const assets: AssetListResponse['assets'] = [];
    let cursor: string | null | undefined;
    for (let page = 0; page < MAX_ASSET_PAGES; page += 1) {
      const response = await this.listAssetPage({ ...filter, limit: ASSET_PAGE_SIZE, cursor });
      assets.push(...response.assets);
      if (!response.has_more || !response.next_cursor) {
        break;
      }
      cursor = response.next_cursor;
    }
    return { assets, next_cursor: null, has_more: false };
  }

  /** One page of assets, newest first; pass the previous page's `next_cursor` for the next one. */
  async listAssetPage(options: ListAssetsOptions = {}): Promise<AssetListResponse> {
    const query: AssetListQuery = { limit: options.limit ?? ASSET_PAGE_SIZE };
    if (options.type) query.type = options.type;
    if (options.module) query.module = options.module;
    if (options.cursor) query.cursor = options.cursor;
    return this.call(() => this.api.GET('/api/assets', { params: { query } }));
  }

  async listVoiceLibrary(): Promise<AssetListResponse> {
    return this.call(() => this.api.GET('/api/voice-library'));
  }

  async getAssetContent(assetId: string): Promise<AssetContentResponse> {
    return this.call(() => this.api.GET('/api/assets/{asset_id}/content', { params: { path: { asset_id: assetId } } }));
  }

  async deleteVoiceAsset(assetId: string): Promise<{ ok: boolean; asset_id: string; deleted: boolean; file_deleted: boolean }> {
    const result = await this.call(() => this.api.DELETE('/api/voice-cloning/assets/{asset_id}', { params: { path: { asset_id: assetId } } }));
    return result as unknown as { ok: boolean; asset_id: string; deleted: boolean; file_deleted: boolean };
  }

  async saveStoryAsset(request: SaveStoryAssetRequest): Promise<SavedStoryAssetResponse> {
    return this.call(() => this.api.POST('/api/assets/story', { body: request }));
  }

  async previewLegacyNonImageAssetImport(): Promise<AssetLegacyImportDryRun> {
    return this.call(() => this.api.POST('/api/assets/migrations/legacy-non-image/dry-run'));
  }

  async listReports(): Promise<ReportListResponse> {
    return this.call(() => this.api.GET('/api/reports'));
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
        // Test doubles may omit headers.
        throw new ApiError(response.status, text, response.headers?.get('x-request-id') ?? undefined);
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
