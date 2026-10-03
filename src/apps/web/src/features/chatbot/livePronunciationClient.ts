import type { components } from '../../api/generated/types';
import { api, unwrapAs } from '../../api/http';
export type PronunciationEntry = components['schemas']['PronunciationEntry'];

export type PronunciationListResponse = components['schemas']['PronunciationListResponse'];

export const ACTIVE_PRONUNCIATIONS_KEY = 'omnix.liveConversation.activePronunciations';
export const PRONUNCIATIONS_CHANGED_EVENT = 'omnix:live-conversation-pronunciations-changed';

function pronunciations(call: Promise<{ data?: PronunciationListResponse; error?: unknown; response: Response }>): Promise<PronunciationListResponse> {
  return unwrapAs(call, (error) => `Pronunciation request failed with status ${error.status}.`);
}

export const livePronunciationClient = {
  list: (sessionId: string) =>
    pronunciations(api.GET('/api/chat/sessions/{session_id}/live-conversation/pronunciations', { params: { path: { session_id: sessionId } } })),
  create: (sessionId: string, phrase: string, pronunciation: string, locale = 'en-US') =>
    pronunciations(api.POST('/api/chat/sessions/{session_id}/live-conversation/pronunciations', {
      params: { path: { session_id: sessionId } },
      body: { phrase, pronunciation, locale },
    })),
  delete: (sessionId: string, entryId: string) =>
    pronunciations(api.DELETE('/api/chat/sessions/{session_id}/live-conversation/pronunciations/{entry_id}', {
      params: { path: { session_id: sessionId, entry_id: entryId } },
    })),
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
