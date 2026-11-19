import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LiveConversationProfile } from '../chat/liveConversationProfileClient';
import { ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, emitOmnixEvent } from '../../../events/bus';
import { companionInitiativeArbiter } from './companion-initiative-arbiter';
import { liveCallPresentationStore } from './live-call-presentation-store';
import {
  callTasksAwaitingReport,
  cancelLiveCallTask,
  initializeLiveCallTasksController,
  LIVE_CALL_TASK_POLL_MS,
  liveCallTasksStore,
  openCallTasks,
  type LiveCallTask,
} from './live-call-tasks-controller';
import { initializeLiveConversationInitiativeController } from './live-conversation-initiative-controller';
import { decideTaskReport } from './live-conversation-initiative-policy';
import { liveConversationStore } from './live-conversation-store';

const TASKS_PATH = '/api/chat/sessions/s1/live-call/tasks';
const CANDIDATE_PATH = '/api/chat/sessions/s1/live-call/initiative-candidate';
const STREAM_PATH = '/api/chat/sessions/s1/live-call/greeting/stream';
const DELIVERY_PATH = '/api/chat/sessions/s1/live-conversation/proactive/delivery';

function task(patch: Partial<LiveCallTask> = {}): LiveCallTask {
  return {
    task_id: 'call-task:m1:0',
    ability: 'deep_research',
    query: 'flights to Lisbon in March',
    state: 'open',
    asked_at: '2026-11-15T10:00:00Z',
    settled_at: null,
    result_message_id: null,
    reported: false,
    ...patch,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function sse(events: unknown[]): Response {
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  return new URL(raw, window.location.origin);
}

type Call = { url: URL; method: string; body: unknown };

let tasks: LiveCallTask[] = [];
let candidate: string | null = null;
let calls: Call[] = [];
let disposers: Array<() => void> = [];

function callsTo(path: string): Call[] {
  return calls.filter((call) => call.url.pathname === path);
}

beforeEach(() => {
  tasks = [];
  candidate = null;
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = requestUrl(input);
    const method = (init?.method ?? request?.method ?? 'GET').toUpperCase();
    const text = typeof init?.body === 'string' ? init.body : request ? await request.clone().text() : '';
    calls.push({ url, method, body: text ? JSON.parse(text) : null });
    if (url.pathname === TASKS_PATH) return json({ tasks });
    if (url.pathname.endsWith('/cancel')) {
      const cancelled = task({ ...tasks[0], state: 'cancelled', settled_at: '2026-11-15T10:01:00Z' });
      tasks = [cancelled];
      return json(cancelled);
    }
    if (url.pathname === CANDIDATE_PATH) return json({ reason: candidate });
    if (url.pathname === STREAM_PATH) {
      const reason = url.searchParams.get('initiative_reason') ?? '';
      const taskId = reason.replace(/^task_report:/, '');
      return sse([
        { type: 'initiative', turn_id: `task-report:${taskId}`, initiative_reason: reason },
        { type: 'complete', content: 'The cheapest flight is on the 12th. The full write-up is in the chat.' },
        { type: 'done' },
      ]);
    }
    if (url.pathname === DELIVERY_PATH) {
      // The server records the report as delivered and names no candidate for it again.
      candidate = null;
      tasks = tasks.map((item) => ({ ...item, reported: true }));
      return json({ message_id: 'p1', committed: true });
    }
    return json(null);
  }));
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  companionInitiativeArbiter.reset();
});

afterEach(() => {
  disposers.forEach((dispose) => dispose());
  disposers = [];
  vi.useRealTimers();
  vi.unstubAllGlobals();
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
});

function connectCall(): void {
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, { token: 1, timestamp: '2026-11-15T10:00:00Z' });
}

describe('a task report decision', () => {
  const free = {
    callConnected: true,
    autoSpeak: true,
    assistantActive: false,
    userSpeaking: false,
    partialTranscript: '',
    requestInFlight: false,
  };

  it('speaks as soon as the floor is free', () => {
    expect(decideTaskReport(free)).toEqual({ action: 'speak', reason: 'task_report_due', eligibleInMs: 0 });
  });

  it('obeys the floor and a closed call', () => {
    expect(decideTaskReport({ ...free, userSpeaking: true }).reason).toBe('user_floor_active');
    expect(decideTaskReport({ ...free, partialTranscript: 'and then' }).reason).toBe('user_floor_active');
    expect(decideTaskReport({ ...free, assistantActive: true }).reason).toBe('assistant_busy');
    expect(decideTaskReport({ ...free, requestInFlight: true }).reason).toBe('assistant_busy');
    expect(decideTaskReport({ ...free, autoSpeak: false }).action).toBe('wait');
    expect(decideTaskReport({ ...free, callConnected: false })).toMatchObject({ action: 'suppress', reason: 'call_not_connected' });
  });
});

describe('the call task list', () => {
  it('waits for settled, unreported tasks only, and needs no report for a cancelled one', () => {
    const state = {
      sessionId: 's1',
      cancelling: [],
      tasks: [
        task({ task_id: 'a', state: 'open' }),
        task({ task_id: 'b', state: 'completed' }),
        task({ task_id: 'c', state: 'failed', reported: true }),
        task({ task_id: 'd', state: 'cancelled' }),
        task({ task_id: 'e', state: 'not_started' }),
      ],
    };

    expect(openCallTasks(state).map((item) => item.task_id)).toEqual(['a']);
    expect(callTasksAwaitingReport('s1', state).map((item) => item.task_id)).toEqual(['b', 'e']);
    expect(callTasksAwaitingReport('other', state)).toEqual([]);
  });

  it('polls every five seconds while a task is open and stops when none is', async () => {
    vi.useFakeTimers();
    tasks = [task()];
    disposers.push(initializeLiveCallTasksController());
    connectCall();
    await vi.advanceTimersByTimeAsync(0);
    expect(callsTo(TASKS_PATH)).toHaveLength(1);
    expect(liveCallTasksStore.getState().tasks).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(LIVE_CALL_TASK_POLL_MS);
    expect(callsTo(TASKS_PATH)).toHaveLength(2);

    tasks = [task({ state: 'completed', settled_at: '2026-11-15T10:02:00Z', result_message_id: 'r1' })];
    await vi.advanceTimersByTimeAsync(LIVE_CALL_TASK_POLL_MS);
    expect(callsTo(TASKS_PATH)).toHaveLength(3);
    expect(callTasksAwaitingReport('s1').map((item) => item.task_id)).toEqual(['call-task:m1:0']);

    await vi.advanceTimersByTimeAsync(LIVE_CALL_TASK_POLL_MS * 3);
    expect(callsTo(TASKS_PATH)).toHaveLength(3);
  });

  it('reads the list again when a reply finishes playing', async () => {
    vi.useFakeTimers();
    disposers.push(initializeLiveCallTasksController());
    connectCall();
    await vi.advanceTimersByTimeAsync(0);
    expect(callsTo(TASKS_PATH)).toHaveLength(1);

    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'idle' } });
    await vi.advanceTimersByTimeAsync(0);
    expect(callsTo(TASKS_PATH)).toHaveLength(2);
  });

  it('cancels a task through its own route and shows the server state', async () => {
    tasks = [task()];
    disposers.push(initializeLiveCallTasksController());
    connectCall();
    await vi.waitFor(() => expect(liveCallTasksStore.getState().tasks).toHaveLength(1));

    await cancelLiveCallTask('call-task:m1:0');

    const cancel = callsTo('/api/chat/sessions/s1/live-call/tasks/call-task%3Am1%3A0/cancel');
    expect(cancel).toHaveLength(1);
    expect(cancel[0].method).toBe('POST');
    await vi.waitFor(() => expect(liveCallTasksStore.getState().tasks[0].state).toBe('cancelled'));
    expect(callTasksAwaitingReport('s1')).toEqual([]);
  });
});

describe('a task report in the call', () => {
  function quietProfile(): LiveConversationProfile {
    // Social initiative is off and its idle threshold far away: only the report can speak.
    return {
      initiative_mode: 'off',
      idle_threshold_ms: 600_000,
      max_idle_prompts: 0,
      long_pause_behavior: 'wait',
      presence_preset: 'calm',
      conversation_stance: 'companion',
    } as unknown as LiveConversationProfile;
  }

  function startCall(): void {
    liveCallPresentationStore.update({ autoSpeak: true });
    liveConversationStore.dispatch({ type: 'profile', profile: quietProfile() });
    disposers.push(initializeLiveCallTasksController());
    disposers.push(initializeLiveConversationInitiativeController());
    connectCall();
  }

  it('asks the server which report is due, speaks it, and commits it under its own turn', async () => {
    tasks = [task({ state: 'completed', settled_at: '2026-11-15T10:02:00Z', result_message_id: 'r1' })];
    candidate = 'task_report:call-task:m1:0';
    // A hidden tab does not hold back what the person asked for.
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    startCall();

    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 4_000 });
    expect(callsTo(CANDIDATE_PATH).length).toBeGreaterThanOrEqual(1);
    const stream = callsTo(STREAM_PATH)[0];
    expect(stream.method).toBe('POST');
    expect(stream.url.searchParams.get('purpose')).toBe('proactive_reengagement');
    expect(stream.url.searchParams.get('initiative_reason')).toBe('task_report:call-task:m1:0');
    // The server builds the report from its record; the call sends no summary of its own.
    expect(stream.url.searchParams.has('state_summary')).toBe(false);

    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'idle' } });

    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(1));
    expect(callsTo(DELIVERY_PATH)[0].body).toEqual({
      turn_id: 'task-report:call-task:m1:0',
      content: 'The cheapest flight is on the 12th. The full write-up is in the chat.',
      initiative_reason: 'task_report:call-task:m1:0',
      delivery_status: 'completed',
    });
    await vi.waitFor(() => expect(companionInitiativeArbiter.snapshot().lastDeliveredSource).toBe('task'));
  });

  it('waits while the person holds the floor', async () => {
    tasks = [task({ state: 'failed', settled_at: '2026-11-15T10:02:00Z' })];
    candidate = 'task_report:call-task:m1:0';
    startCall();
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'user_turn', value: 'paused' } });

    await vi.waitFor(() => expect(callsTo(CANDIDATE_PATH).length).toBeGreaterThanOrEqual(1), { timeout: 3_000 });
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);

    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'user_turn', value: 'idle' } });
    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 3_000 });
  });

  it('starts no report the server did not name', async () => {
    tasks = [task({ state: 'completed', settled_at: '2026-11-15T10:02:00Z', result_message_id: 'r1' })];
    candidate = null;
    startCall();

    await vi.waitFor(() => expect(callsTo(CANDIDATE_PATH).length).toBeGreaterThanOrEqual(1), { timeout: 3_000 });
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
  });
});
