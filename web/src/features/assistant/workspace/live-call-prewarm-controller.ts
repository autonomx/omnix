import type { components } from '../api/generated';
import { createApi } from '../api/gateway';
import { liveConversationStore } from './live-conversation-store';
import { pipelineFetch } from '../../../api/fetchPipeline';
import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, ASSISTANT_VOICE_PERF_EVENT, CHARACTER_AVATAR_RUNTIME_EVENT, emitOmnixEvent } from '../../../events/bus';

let liveCallPrewarmInstalled = false;

const PREWARM_TTL_MS = 5 * 60_000;
const PREWARM_RETRY_MS = 5_000;
const CALL_ID_HEADER = 'X-Omnix-Call-Id';

type LiveCallRuntime = components['schemas']['CharacterLiveCallRuntime'];

// The live-call runtime names no language; English is the voice default.
const PREWARM_LANGUAGE = 'English';

const warmedAt = new Map<string, number>();
const attemptedAt = new Map<string, number>();
const inflight = new Map<string, Promise<void>>();
// Who a chat is talking to: what a turn finds waiting was started for that identity's prompt, so a chat switched to
// another identity needs warming again, however recently it was warmed.
let chatIdentity = '';

export function initializeLiveCallPrewarmController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  if (liveCallPrewarmInstalled) return () => undefined;
  liveCallPrewarmInstalled = true;

  const prewarmActiveSession = () => {
    const sessionId = liveConversationStore.getState().sessionId;
    if (!sessionId) return;
    void prewarmLiveCall(sessionId);
  };
  const followIdentity = (event: Event) => {
    const runtime = (event as CustomEvent<Partial<LiveCallRuntime> | null>).detail;
    if (runtime) chatIdentity = identityOf(runtime);
  };
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, prewarmActiveSession);
  window.addEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, prewarmActiveSession);
  window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, followIdentity);

  return () => {
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, prewarmActiveSession);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, prewarmActiveSession);
    window.removeEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, followIdentity);
    chatIdentity = '';
    liveCallPrewarmInstalled = false;
  };
}

function identityOf(runtime: Partial<LiveCallRuntime>): string {
  return [runtime.interaction_mode, runtime.character_id, runtime.character_profile_version].join(':');
}

export async function prewarmLiveCall(
  sessionId: string,
  fetchImpl: typeof fetch = pipelineFetch,
): Promise<void> {
  const key = `${sessionId}|${chatIdentity}`;
  const existing = inflight.get(key);
  if (existing) return existing;

  const currentTime = Date.now();
  const lastWarm = warmedAt.get(key) ?? 0;
  if (currentTime - lastWarm <= PREWARM_TTL_MS) return;
  const lastAttempt = attemptedAt.get(key) ?? 0;
  if (currentTime - lastAttempt <= PREWARM_RETRY_MS) return;
  attemptedAt.set(key, currentTime);

  const task = runPrewarm(sessionId, key, fetchImpl)
    .finally(() => inflight.delete(key));
  inflight.set(key, task);
  return task;
}

async function runPrewarm(
  sessionId: string,
  key: string,
  fetchImpl: typeof fetch,
): Promise<void> {
  const startedAt = now();
  dispatchPerformance('live_call_prewarm_started', { sessionId });
  try {
    const client = createApi({ fetchImpl });
    const speaker = resolveSpeaker(await fetchRuntime(client, sessionId));
    const language = PREWARM_LANGUAGE;
    const warm = (headers?: Record<string, string>) => client.POST('/api/live-call/sessions/{session_id}/prewarm', {
      params: { path: { session_id: sessionId } },
      body: { speaker, language },
      keepalive: true,
      headers,
    });
    // What a turn finds waiting is held per gateway process, and a call's turns run in two: the worker for speculative
    // ones, the call's replica for the rest. The call's id reaches the replica (the same process, with no replicas).
    const onReplica = warm({ [CALL_ID_HEADER]: encodeURIComponent(sessionId) }).catch(() => null);
    const { data, error, response } = await warm();
    void onReplica;
    // The prewarm route answers with an untyped status object, on failure too.
    const payload = asRecord(data ?? error);
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
      warmedAt.set(key, Date.now());
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

async function fetchRuntime(client: ReturnType<typeof createApi>, sessionId: string): Promise<LiveCallRuntime | null> {
  try {
    const { data } = await client.GET('/api/chat/sessions/{session_id}/live-call/runtime', {
      params: { path: { session_id: sessionId } },
      cache: 'no-store',
    });
    return data ?? null;
  } catch {
    return null;
  }
}

function resolveSpeaker(runtime: LiveCallRuntime | null): string | null {
  return runtime?.voice_speaker_id?.trim() || null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null;
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
  emitOmnixEvent(ASSISTANT_VOICE_PERF_EVENT, {
      stage,
      timestamp: new Date().toISOString(),
      ...detail,
    });
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}