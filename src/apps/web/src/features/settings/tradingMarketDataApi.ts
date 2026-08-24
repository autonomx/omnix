export type CoinMarketCapCredentialStatus = {
  provider: 'coinmarketcap';
  configured: boolean;
  api_key_masked: string;
  api_key_source: 'environment' | 'os_protected_store' | 'missing';
  api_key_editable: boolean;
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
    throw new Error(`Trading market-data request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingMarketDataApi = {
  coinmarketcapCredentials: () => requestJson<CoinMarketCapCredentialStatus>(
    '/api/trading/market-data/providers/coinmarketcap/credentials',
  ),
  saveCoinMarketCapCredentials: (input: { api_key?: string; clear_api_key?: boolean }) => requestJson<CoinMarketCapCredentialStatus>(
    '/api/trading/market-data/providers/coinmarketcap/credentials',
    { method: 'PUT', body: JSON.stringify(input) },
  ),
};
