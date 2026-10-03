import type { components } from '../../api/generated/types';
export type CoinMarketCapCredentialStatus = components['schemas']['CoinMarketCapCredentialStatus'];

export type IbkrSettings = {
  enabled: boolean;
  monitor_enabled: boolean;
  host: string;
  port: number;
  client_id: number;
  live_authority_enabled: boolean;
  recovery_authority_enabled: boolean;
};

export type IbkrSettingsStatus = components['schemas']['IbkrSettingsStatus'];

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
  ibkrSettings: () => requestJson<IbkrSettingsStatus>(
    '/api/trading/market-data/providers/ibkr/settings',
  ),
  saveIbkrSettings: (input: Partial<IbkrSettings>) => requestJson<IbkrSettingsStatus>(
    '/api/trading/market-data/providers/ibkr/settings',
    { method: 'PUT', body: JSON.stringify(input) },
  ),
};
