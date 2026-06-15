import type { components, paths } from './generated/types';

export type GatewayApiPaths = paths;
export type GatewayApiPath = keyof GatewayApiPaths & string;
export type AssetListResponse = components['schemas']['AssetListResponse'];
export type CancelJobRequest = components['schemas']['CancelJobRequest'];
export type ChatSession = components['schemas']['ChatSession'];
export type ChatSessionListResponse = components['schemas']['ChatSessionListResponse'];
export type CreateChatSessionRequest = components['schemas']['CreateChatSessionRequest'];
export type CreateJobRequest = components['schemas']['CreateJobRequest'];
export type DiagnosticsPayload = components['schemas']['DiagnosticsPayload'];
export type JobListResponse = components['schemas']['JobListResponse'];
export type JobRecord = components['schemas']['JobRecord'];
export type PersistenceInventory = components['schemas']['PersistenceInventory'];
export type ProviderFacadePayload = components['schemas']['ProviderFacadePayload'];
export type ReportListResponse = components['schemas']['ReportListResponse'];
export type SendChatMessageRequest = components['schemas']['SendChatMessageRequest'];
export type SendChatMessageResponse = components['schemas']['SendChatMessageResponse'];
export type SettingsPayload = components['schemas']['SettingsPayload'];
export type SettingsSaveResponse = components['schemas']['SettingsSaveResponse'];

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
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

  async post<TRequest, TResponse>(path: `/api/${string}`, body: TRequest): Promise<TResponse> {
    return this.request<TResponse>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
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

  async listJobs(): Promise<JobListResponse> {
    return this.get<JobListResponse>('/api/jobs');
  }

  async createJob(request: CreateJobRequest): Promise<JobRecord> {
    return this.post<CreateJobRequest, JobRecord>('/api/jobs', request);
  }

  async cancelJob(jobId: string, reason: string): Promise<JobRecord> {
    return this.post<CancelJobRequest, JobRecord>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { reason });
  }

  async listAssets(): Promise<AssetListResponse> {
    return this.get<AssetListResponse>('/api/assets');
  }

  async listReports(): Promise<ReportListResponse> {
    return this.get<ReportListResponse>('/api/reports');
  }

  async getReplayPersistenceInventory(): Promise<PersistenceInventory> {
    return this.get<PersistenceInventory>('/api/replay/persistence/inventory');
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

  private async request<T>(path: `/api/${string}`, init: RequestInit): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    const text = await response.text();

    if (!response.ok) {
      throw new ApiError(response.status, text);
    }

    if (!text) {
      return undefined as T;
    }

    return JSON.parse(text) as T;
  }
}

export const omnixApiClient = new OmnixApiClient();
