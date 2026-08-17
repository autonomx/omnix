export type PronunciationEntry = {
  id: string;
  phrase: string;
  pronunciation: string;
  locale: string;
  created_at: string;
  updated_at: string;
};

export type PronunciationListResponse = {
  session_id: string;
  entries: PronunciationEntry[];
};

export const ACTIVE_PRONUNCIATIONS_KEY = 'omnix.liveConversation.activePronunciations';
export const PRONUNCIATIONS_CHANGED_EVENT = 'omnix:live-conversation-pronunciations-changed';

async function request(url: string, init?: RequestInit): Promise<PronunciationListResponse> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!response.ok) throw new Error(`Pronunciation request failed with status ${response.status}.`);
  return response.json() as Promise<PronunciationListResponse>;
}

export const livePronunciationClient = {
  list: (sessionId: string) => request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/live-conversation/pronunciations`),
  create: (sessionId: string, phrase: string, pronunciation: string, locale = 'en-US') => request(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-conversation/pronunciations`,
    { method: 'POST', body: JSON.stringify({ phrase, pronunciation, locale }) },
  ),
  delete: (sessionId: string, entryId: string) => request(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-conversation/pronunciations/${encodeURIComponent(entryId)}`,
    { method: 'DELETE' },
  ),
};

export function publishActivePronunciations(entries: PronunciationEntry[]): void {
  if (typeof window === 'undefined') return;
  try { window.localStorage.setItem(ACTIVE_PRONUNCIATIONS_KEY, JSON.stringify(entries)); } catch { /* event remains authoritative */ }
  window.dispatchEvent(new CustomEvent(PRONUNCIATIONS_CHANGED_EVENT, { detail: { entries } }));
}

export function readActivePronunciations(): PronunciationEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(ACTIVE_PRONUNCIATIONS_KEY) || '[]');
    return Array.isArray(value) ? value.filter((entry) => entry && typeof entry.phrase === 'string' && typeof entry.pronunciation === 'string').slice(0, 32) : [];
  } catch {
    return [];
  }
}
