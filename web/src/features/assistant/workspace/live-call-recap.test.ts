import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_STOP_EVENT, emitOmnixEvent } from '../../../events/bus';
import {
  initializeLiveCallRecap,
  LIVE_CALL_RECAP_DELAY_MS,
  LIVE_CALL_RECAP_POLL_MS,
} from './live-call-recap';
import { liveConversationStore } from './live-conversation-store';

const RECAP_PATH = '/api/chat/sessions/s1/live-call/recap';
const STARTED_AT = '2026-11-23T10:00:00.000Z';

type Call = { path: string; method: string; body: unknown };

let calls: Call[] = [];
let recapStatus: 'started' | 'too_short' = 'started';
let jobStatus = 'running';
let dispose: () => void = () => undefined;

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  vi.useFakeTimers();
  calls = [];
  recapStatus = 'started';
  jobStatus = 'running';
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    const method = (init?.method ?? request?.method ?? 'GET').toUpperCase();
    const text = typeof init?.body === 'string' ? init.body : request ? await request.clone().text() : '';
    calls.push({ path, method, body: text ? JSON.parse(text) : null });
    if (path === RECAP_PATH) return json(recapStatus === 'started' ? { status: 'started', job_id: 'job:1' } : { status: 'too_short', job_id: null });
    if (path === '/api/jobs/job%3A1' || path === '/api/jobs/job:1') return json({ id: 'job:1', status: jobStatus });
    return json(null);
  }));
  liveConversationStore.reset();
});

afterEach(() => {
  dispose();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function startCall(queryClient: QueryClient): void {
  dispose = initializeLiveCallRecap(queryClient);
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, { token: 1, timestamp: STARTED_AT });
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, { token: 1, timestamp: STARTED_AT, chatSessionId: 's1' });
}

describe('call recap', () => {
  it('asks once, after the stop, with the call start, and refreshes the chat when the recap is written', async () => {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    startCall(queryClient);

    emitOmnixEvent(ASSISTANT_LIVE_VOICE_STOP_EVENT);
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_STOP_EVENT);  // a second stop is not a second call
    expect(calls).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_DELAY_MS);
    expect(calls.filter((call) => call.path === RECAP_PATH)).toEqual([
      { path: RECAP_PATH, method: 'POST', body: { call_started_at: STARTED_AT } },
    ]);

    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_POLL_MS);
    expect(invalidate).not.toHaveBeenCalled();
    jobStatus = 'completed';
    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_POLL_MS);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['feature', 'chatbot', 'session', 's1'], exact: true });
  });

  it('does nothing more when the call was too short, and nothing without a chat', async () => {
    const queryClient = new QueryClient();
    startCall(queryClient);
    recapStatus = 'too_short';
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_STOP_EVENT);
    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_DELAY_MS + LIVE_CALL_RECAP_POLL_MS * 3);
    expect(calls.map((call) => call.path)).toEqual([RECAP_PATH]);

    liveConversationStore.reset();
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, { token: 2, timestamp: STARTED_AT });
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_STOP_EVENT);
    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_DELAY_MS);
    expect(calls).toHaveLength(1);
  });

  it("recaps into the call's chat when selecting another chat is what ended it", async () => {
    startCall(new QueryClient());
    liveConversationStore.dispatch({ type: 'session', sessionId: 's2' });
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_STOP_EVENT);  // the controller ends the call after the selection moved
    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_DELAY_MS);
    expect(calls.map((call) => call.path)).toEqual([RECAP_PATH]);
  });

  it('asks nothing for a start that never connected', async () => {
    dispose = initializeLiveCallRecap(new QueryClient());
    liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, { token: 1, timestamp: STARTED_AT });
    emitOmnixEvent(ASSISTANT_LIVE_VOICE_STOP_EVENT);  // e.g. leaving Chat after the microphone was refused
    await vi.advanceTimersByTimeAsync(LIVE_CALL_RECAP_DELAY_MS);
    expect(calls).toHaveLength(0);
  });
});
