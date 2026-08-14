export type LiveMaterialResponsePolicy = 'none' | 'observe' | 'respond';
export type LiveMaterialRetention = 'ephemeral_session' | 'visible_transcript' | 'durable_conversation';

export type LiveMaterialAppendRequest = {
  segment_id: string;
  sequence: number;
  text: string;
  start_sample?: number;
  end_sample?: number;
  response_policy?: LiveMaterialResponsePolicy;
  retention?: LiveMaterialRetention;
  task_contract_id?: string;
  task_contract_version?: number;
};

export type LiveMaterialAcknowledgement = {
  segment_id: string;
  accepted_sequence: number;
  context_version: number;
  task_contract_id: string;
  task_contract_version: number;
  retention: LiveMaterialRetention;
  response_policy: LiveMaterialResponsePolicy;
  idempotent: boolean;
  exact_segment_count: number;
  exact_text_chars: number;
  security: {
    instruction_authority: 'none';
    tool_eligibility: 'none';
    memory_write_eligibility: false;
    task_contract_mutation: false;
  };
};

export type LiveTaskContractAcknowledgementRequest = {
  task_contract_id: string;
  task_contract_version: number;
};

export type LiveTaskContractAcknowledgement = {
  session_id: string;
  task_contract_id: string;
  task_contract_version: number;
  context_version: number;
  idempotent: boolean;
};

export type LiveMaterialSnapshot = {
  session_id: string;
  context_version: number;
  accepted_sequence: number;
  exact_segment_count: number;
  exact_text_chars: number;
  summary_chars: number;
  retention: LiveMaterialRetention;
  task_contract_id: string;
  task_contract_version: number;
};

export class LiveMaterialClient {
  constructor(
    private readonly fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
    private readonly basePath = '/api/chat/sessions',
  ) {}

  async append(sessionId: string, request: LiveMaterialAppendRequest): Promise<LiveMaterialAcknowledgement> {
    return this.request<LiveMaterialAcknowledgement>(this.path(sessionId), {
      method: 'POST',
      body: JSON.stringify({
        start_sample: 0,
        end_sample: 0,
        response_policy: 'none',
        retention: 'ephemeral_session',
        task_contract_id: 'default',
        task_contract_version: 1,
        ...request,
      }),
    });
  }

  async acknowledgeTaskContract(
    sessionId: string,
    request: LiveTaskContractAcknowledgementRequest,
  ): Promise<LiveTaskContractAcknowledgement> {
    return this.request<LiveTaskContractAcknowledgement>(`${this.path(sessionId)}/task-contract`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async snapshot(sessionId: string): Promise<LiveMaterialSnapshot> {
    return this.request<LiveMaterialSnapshot>(this.path(sessionId));
  }

  async clear(sessionId: string): Promise<{ ok: boolean; cleared: boolean }> {
    return this.request(this.path(sessionId), { method: 'DELETE' });
  }

  async promote(
    sessionId: string,
    retention: Exclude<LiveMaterialRetention, 'ephemeral_session'>,
  ): Promise<{ session_id: string; context_version: number; retention: string; content: string; content_chars: number }> {
    return this.request(`${this.path(sessionId)}/promote`, {
      method: 'POST',
      body: JSON.stringify({ retention }),
    });
  }

  private path(sessionId: string): string {
    return `${this.basePath}/${encodeURIComponent(sessionId)}/live/material`;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(path, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init.headers ?? {}) },
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`Live material request failed (${response.status}): ${body}`);
    }
    return response.json() as Promise<T>;
  }
}

export const liveMaterialClient = new LiveMaterialClient();
