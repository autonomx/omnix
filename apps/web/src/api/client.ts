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
    this.fetchImpl = options.fetchImpl ?? fetch;
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
