import { liveConversationStore } from './live-conversation-store';

const INSTALLED_KEY = '__omnixLiveCallPrewarmInstalled';
const LIVE_VOICE_CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const LIVE_VOICE_USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const PERF_EVENT = 'omnix:assistant-voice-perf';
const PREWARM_TTL_MS = 5 * 60_000;
const PREWARM_RETRY_MS = 5_000;

type PrewarmWindow = Window & typeof globalThis & {
  __omnixLiveCallPrewarmInstalled?: boolean;
};

type RuntimePayload = {
  voice_speaker_id?: string | null;
  voiceSpeakerId?: string | null;
  language?: string | null;
  voice?: {
    speaker_id?: string | null;
    speakerId?: string | null;
    language?: string | null;
  } | null;
};

const warmedAt = new Map<string, number>();
const attemptedAt = new Map<string, number>();
const inflight = new Map<string, Promise<void>>();

export function initializeLiveCallPrewarmController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as PrewarmWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;

  const prewarmActiveSession = () => {
    const sessionId = liveConversationStore.getState().sessionId;
    if (!sessionId) return;
    void prewarmLiveCall(sessionId);
  };
  window.addEventListener(LIVE_VOICE_CALL_START_EVENT, prewarmActiveSession);
  window.addEventListener(LIVE_VOICE_USER_SPEECH_EVENT, prewarmActiveSession);

  return () => {
    window.removeEventListener(LIVE_VOICE_CALL_START_EVENT, prewarmActiveSession);
    window.removeEventListener(LIVE_VOICE_USER_SPEECH_EVENT, prewarmActiveSession);
    liveWindow[INSTALLED_KEY] = false;
  };
}

export async function prewarmLiveCall(
  sessionId: string,
  fetchImpl: typeof fetch = window.fetch.bind(window),
): Promise<void> {
  const existing = inflight.get(sessionId);
  if (existing) return existing;

  const currentTime = Date.now();
  const lastWarm = warmedAt.get(sessionId) ?? 0;
  if (currentTime - lastWarm <= PREWARM_TTL_MS) return;
  const lastAttempt = attemptedAt.get(sessionId) ?? 0;
  if (currentTime - lastAttempt <= PREWARM_RETRY_MS) return;
  attemptedAt.set(sessionId, currentTime);

  const task = runPrewarm(sessionId, fetchImpl)
    .finally(() => inflight.delete(sessionId));
  inflight.set(sessionId, task);
  return task;
}

async function runPrewarm(
  sessionId: string,
  fetchImpl: typeof fetch,
): Promise<void> {
  const startedAt = now();
  dispatchPerformance('live_call_prewarm_started', { sessionId });
  try {
    const runtime = await fetchRuntime(fetchImpl, sessionId);
    const speaker = resolveSpeaker(runtime);
    const language = resolveLanguage(runtime);
    const response = await fetchImpl(
      `/api/live-call/sessions/${encodeURIComponent(sessionId)}/prewarm`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speaker, language }),
        keepalive: true,
      },
    );
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(
        typeof payload?.status === 'string'
          ? payload.status
          : `prewarm_failed_${response.status}`,
      );
    }

    const llmStatus = nestedStatus(payload?.llm);
    const ttsStatus = nestedStatus(payload?.tts);
    const fullyWarmed = payload?.fully_warmed === true
      || payload?.cached === true
      || (llmStatus === 'warmed' && ttsStatus === 'warmed');
    const details = {
      sessionId,
      speaker,
      language,
      elapsedMs: now() - startedAt,
      cached: payload?.cached === true,
      status: typeof payload?.status === 'string' ? payload.status : null,
      llmStatus,
      ttsStatus,
    };
    if (fullyWarmed) {
      warmedAt.set(sessionId, Date.now());
      dispatchPerformance('live_call_prewarm_completed', details);
      return;
    }
    dispatchPerformance('live_call_prewarm_partial', details);
  } catch (error) {
    dispatchPerformance('live_call_prewarm_failed', {
      sessionId,
      elapsedMs: now() - startedAt,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function fetchRuntime(
  fetchImpl: typeof fetch,
  sessionId: string,
): Promise<RuntimePayload | null> {
  try {
    const response = await fetchImpl(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/live-call/runtime`,
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      },
    );
    if (!response.ok) return null;
    const payload = await response.json() as unknown;
    return payload && typeof payload === 'object'
      ? payload as RuntimePayload
      : null;
  } catch {
    return null;
  }
}

function resolveSpeaker(payload: RuntimePayload | null): string | null {
  const value = payload?.voice_speaker_id
    ?? payload?.voiceSpeakerId
    ?? payload?.voice?.speaker_id
    ?? payload?.voice?.speakerId
    ?? null;
  return typeof value === 'string' && value.trim()
    ? value.trim()
    : null;
}

function resolveLanguage(payload: RuntimePayload | null): string {
  const value = payload?.language ?? payload?.voice?.language;
  return typeof value === 'string' && value.trim()
    ? value.trim()
    : 'English';
}

async function readJson(
  response: Response,
): Promise<Record<string, unknown> | null> {
  try {
    const payload = await response.json() as unknown;
    return payload && typeof payload === 'object'
      ? payload as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function nestedStatus(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null;
  const status = (value as Record<string, unknown>).status;
  return typeof status === 'string' ? status : null;
}

function dispatchPerformance(
  stage: string,
  detail: Record<string, unknown>,
): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: {
      stage,
      timestamp: new Date().toISOString(),
      ...detail,
    },
  }));
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}