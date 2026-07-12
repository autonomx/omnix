import { useEffect, useState } from 'react';
import type { RpgStoryMessagePreview } from './rpgUiState';

export type RpgTurnUiStatus = 'pending' | 'complete' | 'failed';

export interface RpgTurnVisibleMessage {
  kind?: string;
  speaker_id?: string | null;
  speaker?: string;
  text?: string;
}

export interface RpgTurnVisibleResponse {
  narration?: string;
  messages?: RpgTurnVisibleMessage[];
  plain_text?: string;
}

export interface RpgTurnResponseV2 {
  ok?: boolean;
  contract_version?: string;
  session_id?: string;
  submission_id?: string | null;
  interaction_id?: string | null;
  trace_id?: string | null;
  visible_response?: RpgTurnVisibleResponse;
  response?: string;
  content?: string;
  state?: {
    revision?: number | null;
    changed?: boolean;
    changed_domains?: string[];
  };
  timing?: Record<string, number>;
}

export interface RpgTurnUiEntry extends RpgStoryMessagePreview {
  id: string;
  sessionId: string;
  submissionId: string;
  interactionId?: string;
  status: RpgTurnUiStatus;
}

interface CachedResponse {
  body: string;
  headers: Array<[string, string]>;
  status: number;
  statusText: string;
}

const listeners = new Set<() => void>();
const entriesBySession = new Map<string, RpgTurnUiEntry[]>();
const responseCache = new Map<string, CachedResponse>();
const conversationRefreshSuppression = new Map<string, number>();
let fetchInstalled = false;
let originalFetch: typeof fetch | null = null;
let mountedSubscribers = 0;
let uninstallSharedInterceptor: (() => void) | null = null;

const TURN_PATH = /^\/api\/rpg\/sessions\/([^/]+)\/turn$/;
const SESSION_PATH = /^\/api\/rpg\/sessions\/([^/]+)$/;
const REFRESH_SUPPRESSION_MS = 2_500;
const MAX_ENTRIES_PER_SESSION = 24;

export function createRpgSubmissionId(): string {
  const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  return `submit:${random}`;
}

export function installRpgTurnUiFetchInterceptor(fetchImpl?: typeof fetch): () => void {
  const resolvedFetch = fetchImpl || globalThis.fetch;
  if (fetchInstalled || typeof resolvedFetch !== 'function') {
    return () => undefined;
  }
  fetchInstalled = true;
  originalFetch = resolvedFetch;

  globalThis.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const requestUrl = requestUrlString(input);
    const url = new URL(requestUrl, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    const request = isRequest(input) ? input : null;
    const method = String(init.method || request?.method || 'GET').toUpperCase();
    const turnMatch = url.pathname.match(TURN_PATH);

    if (method === 'GET') {
      const cached = suppressedCachedResponse(url.pathname);
      if (cached) return restoreResponse(cached);
    }

    if (method === 'POST' && turnMatch) {
      const sessionId = decodeURIComponent(turnMatch[1]);
      const headers = new Headers(request?.headers);
      new Headers(init.headers).forEach((value, key) => headers.set(key, value));
      const submissionId = headers.get('X-Omnix-Rpg-Submission-Id')?.trim() || createRpgSubmissionId();
      headers.set('X-Omnix-Rpg-Submission-Id', submissionId);
      const command = readCommand(init.body);
      beginRpgTurnUiSubmission({ sessionId, submissionId, command });
      try {
        const response = await resolvedFetch(input, { ...init, headers });
        if (response.ok) {
          const payload = await safeJson(response.clone());
          completeRpgTurnUiSubmission({ sessionId, submissionId, payload });
          applyRefreshPolicy(sessionId, payload.state?.changed_domains || []);
        } else if (response.status === 404) {
          discardRpgTurnUiSubmission(sessionId, submissionId);
        } else {
          failRpgTurnUiSubmission({ sessionId, submissionId, message: `RPG turn failed with HTTP ${response.status}.` });
        }
        return response;
      } catch (error) {
        failRpgTurnUiSubmission({
          sessionId,
          submissionId,
          message: error instanceof Error ? error.message : 'RPG turn request failed.',
        });
        throw error;
      }
    }

    const response = await resolvedFetch(input, init);
    if (method === 'GET' && response.ok && isCacheableRefreshPath(url.pathname)) {
      void cacheResponse(url.pathname, response.clone());
    }
    return response;
  }) as typeof fetch;

  return () => {
    if (fetchInstalled && originalFetch === resolvedFetch) {
      globalThis.fetch = resolvedFetch;
      originalFetch = null;
      fetchInstalled = false;
    }
  };
}

export function beginRpgTurnUiSubmission({
  sessionId,
  submissionId,
  command,
}: {
  sessionId: string;
  submissionId: string;
  command: string;
}): void {
  const current = entriesBySession.get(sessionId) || [];
  const withoutSubmission = current.filter((entry) => entry.submissionId !== submissionId);
  setSessionEntries(sessionId, [
    ...withoutSubmission,
    {
      id: `${submissionId}:player`,
      sessionId,
      submissionId,
      status: 'pending',
      avatar: '•',
      speaker: 'You',
      text: command || 'Submitting turn…',
      tone: 'player',
    },
    {
      id: `${submissionId}:pending`,
      sessionId,
      submissionId,
      status: 'pending',
      avatar: 'O',
      speaker: 'Omnix (Narrator)',
      text: 'Considering the scene…',
      tone: 'narrator',
    },
  ]);
}

export function completeRpgTurnUiSubmission({
  sessionId,
  submissionId,
  payload,
}: {
  sessionId: string;
  submissionId: string;
  payload: RpgTurnResponseV2;
}): void {
  const current = entriesBySession.get(sessionId) || [];
  const player = current.find((entry) => entry.submissionId === submissionId && entry.tone === 'player');
  const interactionId = payload.interaction_id || undefined;
  const withoutSubmission = current.filter((entry) => entry.submissionId !== submissionId);
  setSessionEntries(sessionId, [
    ...withoutSubmission,
    ...(player ? [{ ...player, status: 'complete' as const, interactionId }] : []),
    ...responseEntries(sessionId, submissionId, interactionId, payload),
  ]);
}

export function failRpgTurnUiSubmission({
  sessionId,
  submissionId,
  message,
}: {
  sessionId: string;
  submissionId: string;
  message: string;
}): void {
  const current = entriesBySession.get(sessionId) || [];
  setSessionEntries(
    sessionId,
    current.map((entry) => entry.submissionId === submissionId && entry.tone !== 'player'
      ? { ...entry, status: 'failed', text: message }
      : entry),
  );
}

export function discardRpgTurnUiSubmission(sessionId: string, submissionId: string): void {
  const current = entriesBySession.get(sessionId) || [];
  setSessionEntries(sessionId, current.filter((entry) => entry.submissionId !== submissionId));
}

export function getRpgTurnUiEntries(sessionId: string): RpgTurnUiEntry[] {
  return [...(entriesBySession.get(sessionId) || [])];
}

export function mergeRpgTurnUiMessages(
  baseMessages: RpgStoryMessagePreview[],
  incrementalEntries: RpgTurnUiEntry[],
): RpgStoryMessagePreview[] {
  const seen = new Set(baseMessages.map((message) => `${message.speaker}\u0000${message.text}`));
  const merged = [...baseMessages];
  for (const entry of incrementalEntries) {
    const key = `${entry.speaker}\u0000${entry.text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(entry);
  }
  return merged.slice(-10);
}

export function useRpgTurnUiMessages(
  sessionId: string,
  baseMessages: RpgStoryMessagePreview[],
): RpgStoryMessagePreview[] {
  const [, setVersion] = useState(0);
  useEffect(() => {
    mountedSubscribers += 1;
    if (mountedSubscribers === 1) {
      uninstallSharedInterceptor = installRpgTurnUiFetchInterceptor();
    }
    const listener = () => setVersion((value) => value + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
      mountedSubscribers = Math.max(0, mountedSubscribers - 1);
      if (mountedSubscribers === 0) {
        uninstallSharedInterceptor?.();
        uninstallSharedInterceptor = null;
        entriesBySession.clear();
        conversationRefreshSuppression.clear();
      }
    };
  }, []);
  return mergeRpgTurnUiMessages(baseMessages, getRpgTurnUiEntries(sessionId));
}

export function refreshPathsForChangedDomains(sessionId: string, changedDomains: string[]): string[] {
  const domains = new Set(changedDomains);
  if (!domains.size || (domains.size === 1 && domains.has('conversation'))) return [];
  const paths = new Set<string>([`/api/rpg/sessions/${encodeURIComponent(sessionId)}`]);
  if (domains.has('inventory') || domains.has('currency') || domains.has('player')) {
    paths.add('/api/replay/inventory');
  }
  if (domains.has('quests') || domains.has('journal') || domains.has('world') || domains.has('location')) {
    paths.add('/api/reports');
  }
  return [...paths];
}

export function resetRpgTurnUiStoreForTests(): void {
  entriesBySession.clear();
  responseCache.clear();
  conversationRefreshSuppression.clear();
  listeners.clear();
  mountedSubscribers = 0;
  uninstallSharedInterceptor?.();
  uninstallSharedInterceptor = null;
  if (fetchInstalled && originalFetch) globalThis.fetch = originalFetch;
  fetchInstalled = false;
  originalFetch = null;
}

function responseEntries(
  sessionId: string,
  submissionId: string,
  interactionId: string | undefined,
  payload: RpgTurnResponseV2,
): RpgTurnUiEntry[] {
  const visible = payload.visible_response || {};
  const entries: RpgTurnUiEntry[] = [];
  if (visible.narration?.trim()) {
    entries.push({
      id: `${interactionId || submissionId}:narration`,
      sessionId,
      submissionId,
      interactionId,
      status: 'complete',
      avatar: 'O',
      speaker: 'Omnix (Narrator)',
      text: visible.narration.trim(),
      tone: 'narrator',
    });
  }
  for (const [index, message] of (visible.messages || []).entries()) {
    const text = message.text?.trim();
    if (!text) continue;
    const speaker = message.speaker?.trim() || 'NPC';
    entries.push({
      id: `${interactionId || submissionId}:message:${index}`,
      sessionId,
      submissionId,
      interactionId,
      status: 'complete',
      avatar: speaker.charAt(0).toUpperCase(),
      speaker,
      text,
      tone: 'npc',
    });
  }
  if (!entries.length) {
    const text = payload.response?.trim() || payload.content?.trim();
    if (text) {
      entries.push({
        id: `${interactionId || submissionId}:response`,
        sessionId,
        submissionId,
        interactionId,
        status: 'complete',
        avatar: 'O',
        speaker: 'Omnix (Narrator)',
        text,
        tone: 'narrator',
      });
    }
  }
  return entries;
}

function readCommand(body: BodyInit | null | undefined): string {
  if (typeof body !== 'string') return '';
  try {
    const payload = JSON.parse(body) as Record<string, unknown>;
    return typeof payload.command === 'string' ? payload.command.trim() : '';
  } catch {
    return '';
  }
}

async function safeJson(response: Response): Promise<RpgTurnResponseV2> {
  try {
    return await response.json() as RpgTurnResponseV2;
  } catch {
    return {};
  }
}

function requestUrlString(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function isRequest(input: RequestInfo | URL): input is Request {
  return typeof Request !== 'undefined' && input instanceof Request;
}

function isCacheableRefreshPath(pathname: string): boolean {
  return SESSION_PATH.test(pathname)
    || pathname === '/api/replay/inventory'
    || pathname === '/api/jobs'
    || pathname === '/api/assets'
    || pathname === '/api/reports';
}

function applyRefreshPolicy(sessionId: string, changedDomains: string[]): void {
  if (refreshPathsForChangedDomains(sessionId, changedDomains).length === 0) {
    conversationRefreshSuppression.set(sessionId, Date.now() + REFRESH_SUPPRESSION_MS);
  }
}

function suppressedCachedResponse(pathname: string): CachedResponse | null {
  const sessionMatch = pathname.match(SESSION_PATH);
  const sessionId = sessionMatch ? decodeURIComponent(sessionMatch[1]) : '';
  const suppressUntil = sessionId
    ? conversationRefreshSuppression.get(sessionId) || 0
    : Math.max(0, ...conversationRefreshSuppression.values());
  if (Date.now() > suppressUntil) return null;
  return responseCache.get(pathname) || null;
}

async function cacheResponse(pathname: string, response: Response): Promise<void> {
  try {
    responseCache.set(pathname, {
      body: await response.text(),
      headers: [...response.headers.entries()],
      status: response.status,
      statusText: response.statusText,
    });
  } catch {
    // Cache misses fall through to the real refresh and never affect gameplay.
  }
}

function restoreResponse(cached: CachedResponse): Response {
  return new Response(cached.body, {
    status: cached.status,
    statusText: cached.statusText,
    headers: cached.headers,
  });
}

function setSessionEntries(sessionId: string, entries: RpgTurnUiEntry[]): void {
  entriesBySession.set(sessionId, entries.slice(-MAX_ENTRIES_PER_SESSION));
  for (const listener of listeners) listener();
}
