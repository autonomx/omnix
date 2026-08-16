import type {
  PaperAccount,
  PaperAccountCreateInput,
  PaperAccountSnapshot,
  PaperOrder,
  PaperOrderInput,
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
