export type AlpacaIexCredentialStatus = {
  provider: 'alpaca_iex';
  configured: boolean;
  api_key_id_masked: string;
  api_key_source: 'environment' | 'os_protected_store' | 'missing';
  secret_key_source: 'environment' | 'os_protected_store' | 'missing';
  api_key_editable: boolean;
  secret_key_editable: boolean;
  storage: string;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading execution request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingExecutionApi = {
  alpacaCredentials: () => requestJson<AlpacaIexCredentialStatus>(
    '/api/trading/execution/providers/alpaca-iex/credentials',
  ),
  saveAlpacaCredentials: (input: {
    api_key_id?: string;
    secret_key?: string;
    clear_api_key_id?: boolean;
    clear_secret_key?: boolean;
  }) => requestJson<AlpacaIexCredentialStatus>(
    '/api/trading/execution/providers/alpaca-iex/credentials',
    { method: 'PUT', body: JSON.stringify(input) },
  ),
};
