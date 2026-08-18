import type {
  PaperAccount,
  PaperAccountCreateInput,
  PaperAccountSnapshot,
  PaperOrder,
  PaperOrderInput,
  PaperPositionProtection,
  PaperProtectionInput,
} from './paperTypes';

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
    throw new Error(`Paper Trading request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingPaperApi = {
  accounts: async () => {
    const payload = await requestJson<unknown>('/api/trading/paper/accounts');
    if (!payload || typeof payload !== 'object') return [];
    const accounts = (payload as Record<string, unknown>).accounts;
    return Array.isArray(accounts) ? accounts as PaperAccount[] : [];
  },
  createAccount: (input: PaperAccountCreateInput) =>
    requestJson<PaperAccountSnapshot>('/api/trading/paper/accounts', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  snapshot: (accountId: string) =>
    requestJson<PaperAccountSnapshot>(`/api/trading/paper/accounts/${encodeURIComponent(accountId)}`),
  placeOrder: (accountId: string, input: PaperOrderInput) =>
    requestJson<PaperOrder>(`/api/trading/paper/accounts/${encodeURIComponent(accountId)}/orders`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  /** @deprecated Browser observations are deliberately non-authoritative. */
  processObservation: async (_accountId: string, _input: unknown) => ({ fills: [] as unknown[] }),
  protections: async (accountId: string) => {
    const payload = await requestJson<{ protections?: PaperPositionProtection[] }>(
      `/api/trading/paper/accounts/${encodeURIComponent(accountId)}/protections?active_only=true`,
    );
    return Array.isArray(payload.protections) ? payload.protections : [];
  },
  protection: async (accountId: string, instrumentId: string) => {
    const response = await fetch(
      `/api/trading/paper/accounts/${encodeURIComponent(accountId)}/protections/${encodeURIComponent(instrumentId)}`,
      { headers: { 'content-type': 'application/json' } },
    );
    if (response.status === 404) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof payload?.detail === 'string'
        ? payload.detail
        : JSON.stringify(payload?.detail ?? payload);
      throw new Error(`Paper Trading request failed (${response.status}): ${detail}`);
    }
    return payload as PaperPositionProtection;
  },
  setProtection: (accountId: string, input: PaperProtectionInput) =>
    requestJson<PaperPositionProtection>(
      `/api/trading/paper/accounts/${encodeURIComponent(accountId)}/protections`,
      { method: 'PUT', body: JSON.stringify(input) },
    ),
  clearProtection: (accountId: string, instrumentId: string) =>
    requestJson<PaperPositionProtection>(
      `/api/trading/paper/accounts/${encodeURIComponent(accountId)}/protections/${encodeURIComponent(instrumentId)}`,
      { method: 'DELETE' },
    ),
  resetAccount: (account: PaperAccount, initialCash: string) =>
    requestJson<PaperAccountSnapshot>(
      `/api/trading/paper/accounts/${encodeURIComponent(account.account_id)}/reset`,
      {
        method: 'POST',
        headers: { 'If-Match': String(account.revision) },
        body: JSON.stringify({ initial_cash: initialCash }),
      },
    ),
  archiveAccount: (account: PaperAccount) =>
    requestJson<PaperAccountSnapshot>(
      `/api/trading/paper/accounts/${encodeURIComponent(account.account_id)}`,
      {
        method: 'DELETE',
        headers: { 'If-Match': String(account.revision) },
      },
    ),
};
