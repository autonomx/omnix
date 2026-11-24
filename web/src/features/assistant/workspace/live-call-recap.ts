import type { QueryClient } from '@tanstack/react-query';

import { unwrap } from '../../../api/http';
import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_STOP_EVENT } from '../../../events/bus';
import { api } from '../api/gateway';
import { liveConversationStore } from './live-conversation-store';

/**
 * Call recap (D3): when a call stops, ask the server for its recap. The server decides whether the call was long
 * enough and writes the recap as one chat message in the background; this module only asks once per call, waits for
 * the job, and refreshes the chat so the message shows.
 */

/** A reply still committing when the call stopped joins the recap. */
export const LIVE_CALL_RECAP_DELAY_MS = 2_500;
export const LIVE_CALL_RECAP_POLL_MS = 2_000;
export const LIVE_CALL_RECAP_WAIT_MS = 120_000;

const SETTLED = new Set(['completed', 'failed', 'canceled', 'stale']);

let callStartedAt: string | null = null;
let callSessionId: string | null = null;
let timers = new Set<ReturnType<typeof setTimeout>>();

function later(callback: () => void, delayMs: number): void {
  const timer = setTimeout(() => {
    timers.delete(timer);
    callback();
  }, delayMs);
  timers.add(timer);
}

function wait(delayMs: number): Promise<void> {
  return new Promise((resolve) => later(resolve, delayMs));
}

export async function requestLiveCallRecap(queryClient: QueryClient, sessionId: string, startedAt: string): Promise<void> {
  const start = await unwrap(api.POST('/api/chat/sessions/{session_id}/live-call/recap', {
    params: { path: { session_id: sessionId } },
    body: { call_started_at: startedAt },
  }));
  if (start.status !== 'started' || !start.job_id) return;
  const deadline = Date.now() + LIVE_CALL_RECAP_WAIT_MS;
  while (Date.now() < deadline) {
    await wait(LIVE_CALL_RECAP_POLL_MS);
    const job = await unwrap(api.GET('/api/jobs/{job_id}', { params: { path: { job_id: start.job_id } }, cache: 'no-store' }));
    if (!SETTLED.has(job.status)) continue;
    if (job.status === 'completed') {
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'session', sessionId], exact: true });
    }
    return;
  }
}

export function initializeLiveCallRecap(queryClient: QueryClient): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const handleStart = (event: Event) => {
    const detail = (event as CustomEvent<{ timestamp?: unknown }>).detail;
    callStartedAt = typeof detail?.timestamp === 'string' ? detail.timestamp : new Date().toISOString();
    callSessionId = null;
  };
  const handleSession = () => {
    // The call's chat is the one it talks to; read while the call is open.
    if (callStartedAt) callSessionId = liveConversationStore.getState().sessionId ?? callSessionId;
  };
  const unsubscribe = liveConversationStore.subscribe(handleSession);
  const handleStop = () => {
    handleSession();
    const startedAt = callStartedAt;
    const sessionId = callSessionId;
    callStartedAt = null;
    callSessionId = null;
    if (!startedAt || !sessionId) return;
    later(() => {
      requestLiveCallRecap(queryClient, sessionId, startedAt).catch(() => undefined);  // a recap is never worth an error
    }, LIVE_CALL_RECAP_DELAY_MS);
  };
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleStart);
  window.addEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
  return () => {
    unsubscribe();
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, handleStart);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_STOP_EVENT, handleStop);
    timers.forEach((timer) => clearTimeout(timer));
    timers = new Set();
    callStartedAt = null;
    callSessionId = null;
  };
}
