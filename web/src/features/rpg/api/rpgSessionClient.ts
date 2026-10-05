import { ApiError, omnixApiClient, type ApiRequestOptions, type CreateJobRequest, type JobRecord } from '../../../api/client';
import { withRpgGenesisContract } from './rpgGenesisPresentation';

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

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

const api = omnixApiClient;

/** The RPG feature's gateway calls; each falls back to the compatibility route when the session route is missing. */
export const rpgSessionClient = {
  async listRpgPresets(): Promise<RpgPresetListResponse> {
    try {
      return await api.get<RpgPresetListResponse>('/api/rpg/presets');
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      const compatibility = await api.post<Record<string, never>, RpgSessionListResponse>('/api/rpg/session/list', {});
      return { ok: compatibility.ok, presets: compatibility.presets ?? [] };
    }
  },

  async listRpgSessions(): Promise<RpgSessionListResponse> {
    try {
      const [sessions, presets] = await Promise.all([api.get<RpgSessionListResponse>('/api/rpg/sessions'), rpgSessionClient.listRpgPresets()]);
      return { ...sessions, presets: presets.presets };
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      return api.post<Record<string, never>, RpgSessionListResponse>('/api/rpg/session/list', {});
    }
  },

  async listRpgSessionSummaries(): Promise<RpgSessionListResponse> {
    return api.get<RpgSessionListResponse>('/api/rpg/sessions');
  },

  async getRpgSession(sessionId: string): Promise<RpgLaunchResponse> {
    return api.get<RpgLaunchResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}`);
  },

  async createRpgNewGame(request: RpgNewGameRequest = {}): Promise<RpgLaunchResponse> {
    const genesisRequest = withRpgGenesisContract(request);
    const traceStartedAt = nowMs();
    const events: RpgLaunchRequestTraceEvent[] = [{ endpoint: '/api/rpg/new-game', method: 'POST', status: 'started' }];
    logRpgLaunchTrace('starting POST /api/rpg/new-game');
    try {
      const startedAt = nowMs();
      const result = await api.post<RpgNewGameRequest, RpgLaunchResponse>('/api/rpg/new-game', genesisRequest);
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
      if (!isNotFound(error)) {
        throw error;
      }
      events.push({ endpoint: '/api/rpg/session/get', method: 'POST', status: 'fallback' });
      logRpgLaunchTrace('falling back to POST /api/rpg/session/get');
      const fallbackStartedAt = nowMs();
      const result = await api.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
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
  },

  async startRpgPreset(presetId: string): Promise<RpgLaunchResponse> {
    try {
      return await api.post<Record<string, never>, RpgLaunchResponse>(`/api/rpg/presets/${encodeURIComponent(presetId)}/start`, {});
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      return api.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
        action: 'start_preset',
        preset_id: presetId,
      });
    }
  },

  async continueRpgSession(sessionId: string): Promise<RpgLaunchResponse> {
    try {
      return await api.post<Record<string, never>, RpgLaunchResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/continue`, {});
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      return api.post<Record<string, unknown>, RpgLaunchResponse>('/api/rpg/session/get', {
        action: 'continue',
        session_id: sessionId,
      });
    }
  },

  async renameRpgSession(sessionId: string, name: string): Promise<RpgSessionMutationResponse> {
    try {
      return await api.post<{ name: string }, RpgSessionMutationResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/rename`, { name });
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      return api.post<Record<string, unknown>, RpgSessionMutationResponse>('/api/rpg/session/get', {
        action: 'rename',
        session_id: sessionId,
        name,
      });
    }
  },

  async deleteRpgSession(sessionId: string): Promise<RpgSessionMutationResponse> {
    try {
      return await api.post<Record<string, never>, RpgSessionMutationResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/delete`, {});
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      return api.post<Record<string, unknown>, RpgSessionMutationResponse>('/api/rpg/session/get', {
        action: 'delete',
        session_id: sessionId,
      });
    }
  },

  async applyRpgLoadoutAction(sessionId: string, request: RpgLoadoutActionRequest): Promise<RpgLoadoutActionResponse> {
    try {
      return await api.post<RpgLoadoutActionRequest, RpgLoadoutActionResponse>(`/api/rpg/sessions/${encodeURIComponent(sessionId)}/loadout-action`, request);
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      return api.post<Record<string, unknown>, RpgLoadoutActionResponse>('/api/rpg/session/get', {
        action: 'loadout_action',
        session_id: sessionId,
        loadout: request,
      });
    }
  },

  /**
   * Applies an `rpg.turn` through the foreground session route and returns it
   * as a completed job; without that route (or a session and command) the
   * request becomes an ordinary queued job.
   */
  async submitTurnJob(request: CreateJobRequest, options: ApiRequestOptions = {}): Promise<JobRecord> {
    const foregroundTurn = await createForegroundTurnJob(request);
    return foregroundTurn ?? api.createJob(request, options);
  },
};

async function createForegroundTurnJob(request: CreateJobRequest): Promise<JobRecord | null> {
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
    result = await api.post<{ command: string }, RpgForegroundTurnResponse>(
      `/api/rpg/sessions/${encodeURIComponent(sessionId)}/turn`,
      { command },
    );
  } catch (error) {
    if (isNotFound(error)) {
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
