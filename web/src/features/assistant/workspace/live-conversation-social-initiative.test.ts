import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LiveConversationProfile } from '../chat/liveConversationProfileClient';
import {
  ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT,
  ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT,
  ASSISTANT_VOICE_PERF_EVENT,
  emitOmnixEvent,
} from '../../../events/bus';
import { companionInitiativeArbiter } from './companion-initiative-arbiter';
import { liveCallPresentationStore } from './live-call-presentation-store';
import {
  initializeLiveCallTasksController,
  liveCallTasksStore,
  refreshLiveCallTasks,
  type LiveCallTask,
} from './live-call-tasks-controller';
import {
  INITIATIVE_ANSWER_WINDOW_MS,
  initializeLiveConversationInitiativeController,
} from './live-conversation-initiative-controller';
import { liveConversationStore } from './live-conversation-store';
import { controller as liveVoiceCall, type LiveVoiceSession } from './live-voice-controller-state';

// Companion 3.1-3.3: social initiative in a quiet call, end to end through the controller with a stubbed server.

const TASKS_PATH = '/api/chat/sessions/s1/live-call/tasks';
const CANDIDATE_PATH = '/api/chat/sessions/s1/live-call/initiative-candidate';
const STREAM_PATH = '/api/chat/sessions/s1/live-call/greeting/stream';
const DELIVERY_PATH = '/api/chat/sessions/s1/live-conversation/proactive/delivery';
const LOOP = `open_loop:${'a'.repeat(24)}`;
const COOLDOWN_MS = 30_000;

type Call = { url: URL; method: string; body: unknown };

let calls: Call[] = [];
let perf: Array<Record<string, unknown>> = [];
let socialCandidate: string | null = null;
let reportCandidate: string | null = null;
let tasks: LiveCallTask[] = [];
let skip = false;
let disposers: Array<() => void> = [];

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function sse(events: unknown[]): Response {
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function callsTo(path: string): Call[] {
  return calls.filter((call) => call.url.pathname === path);
}

function streamReasons(): Array<string | null> {
  return callsTo(STREAM_PATH).map((call) => call.url.searchParams.get('initiative_reason'));
}

function stages(stage: string): Array<Record<string, unknown>> {
  return perf.filter((event) => event.stage === stage);
}

const recordPerf = (event: Event) => perf.push((event as CustomEvent<Record<string, unknown>>).detail);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] });
  vi.setSystemTime(new Date(2026, 10, 15, 14, 0));
  calls = [];
  perf = [];
  socialCandidate = null;
  reportCandidate = null;
  tasks = [];
  skip = false;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, window.location.origin);
    const method = (init?.method ?? request?.method ?? 'GET').toUpperCase();
    const text = typeof init?.body === 'string' ? init.body : request ? await request.clone().text() : '';
    calls.push({ url, method, body: text ? JSON.parse(text) : null });
    if (url.pathname === TASKS_PATH) return json({ tasks });
    if (url.pathname === CANDIDATE_PATH) {
      return json({ reason: reportCandidate ?? (url.searchParams.get('social') === 'true' ? socialCandidate : null) });
    }
    if (url.pathname === STREAM_PATH) {
      const reason = url.searchParams.get('initiative_reason') ?? '';
      const n = callsTo(STREAM_PATH).length - 1;
      const turnId = reason.startsWith('open_loop:')
        ? `open-loop:${reason.slice('open_loop:'.length)}:n${n}`
        : reason.startsWith('task_report:') ? `task-report:${reason.slice('task_report:'.length)}` : `proactive:n${n}`;
      if (skip && !reason.startsWith('task_report:')) {
        return sse([
          { type: 'initiative', turn_id: turnId, initiative_reason: reason },
          { type: 'complete', content: '', metadata: { generation_status: 'skipped', skip_reason: 'social_model_skip' } },
          { type: 'done' },
        ]);
      }
      return sse([
        { type: 'initiative', turn_id: turnId, initiative_reason: reason },
        { type: 'complete', content: 'How did the tracking device go?' },
        { type: 'done' },
      ]);
    }
    if (url.pathname === DELIVERY_PATH) {
      if (reportCandidate) {
        reportCandidate = null;
        tasks = tasks.map((item) => ({ ...item, reported: true }));
      }
      return json({ message_id: 'p1', committed: true });
    }
    return json(null);
  }));
  window.addEventListener(ASSISTANT_VOICE_PERF_EVENT, recordPerf);
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  companionInitiativeArbiter.reset();
});

afterEach(() => {
  disposers.forEach((dispose) => dispose());
  disposers = [];
  window.removeEventListener(ASSISTANT_VOICE_PERF_EVENT, recordPerf);
  liveVoiceCall.activeSession = null;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
});

function profile(patch: Partial<LiveConversationProfile> = {}): LiveConversationProfile {
  return {
    initiative_mode: 'gentle',
    idle_threshold_ms: 1_000,
    max_idle_prompts: 1,
    long_pause_behavior: 'wait',
    presence_preset: 'natural',
    conversation_stance: 'automatic',
    quiet_hours_enabled: false,
    quiet_hours_start: '22:00',
    quiet_hours_end: '08:00',
    max_initiatives_per_hour: 4,
    ...patch,
  } as unknown as LiveConversationProfile;
}

function startCall(patch: Partial<LiveConversationProfile> = {}, withTasks = false): void {
  liveCallPresentationStore.update({ autoSpeak: true });
  liveConversationStore.dispatch({ type: 'profile', profile: profile(patch) });
  if (withTasks) disposers.push(initializeLiveCallTasksController());
  disposers.push(initializeLiveConversationInitiativeController());
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, { token: 1, timestamp: '2026-11-15T14:00:00Z' });
  liveConversationStore.dispatch({ type: 'transcript_final', text: 'I finally started on the tracking device.' });
}

function setSpeaking(speaking: boolean): void {
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: speaking ? 'speaking' : 'idle' } });
}

/** The remark plays to its end (optionally answered while it plays), and the call commits it. */
async function play({ answerWhilePlaying = false } = {}): Promise<void> {
  setSpeaking(true);
  if (answerWhilePlaying) userSpeaks();
  setSpeaking(false);
  await vi.advanceTimersByTimeAsync(0);
}

/**
 * Steps the clock until the call asks for its next remark, then plays it at once: a remark whose audio never starts
 * is dropped after 5 s and asked for again, which a long jump of the clock would count as several remarks.
 */
async function nextRemark(withinMs: number, options: { answerWhilePlaying?: boolean } = {}): Promise<void> {
  const before = callsTo(STREAM_PATH).length;
  for (let waited = 0; waited < withinMs && callsTo(STREAM_PATH).length === before; waited += 250) {
    await vi.advanceTimersByTimeAsync(250);
  }
  expect(callsTo(STREAM_PATH)).toHaveLength(before + 1);
  await play(options);
}

function userSpeaks(): void {
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, {
    timestamp: new Date().toISOString(), rms: 0.05, assistantSpeaking: false, assistantOwnsFloor: false,
  });
}

describe('social initiative reasons in a quiet call', () => {
  it("raises the server's open loop once the call may speak socially", async () => {
    socialCandidate = LOOP;
    startCall();

    await vi.advanceTimersByTimeAsync(2_000);
    const asked = callsTo(CANDIDATE_PATH).filter((call) => call.url.searchParams.get('social') === 'true');
    expect(asked).toHaveLength(1);
    expect(streamReasons()).toEqual([LOOP]);
    // The call still sends its own state; the server puts the loop's text in the prompt.
    expect(callsTo(STREAM_PATH)[0].url.searchParams.get('state_summary')).toContain('recent=I finally started');
    expect(stages('initiative_generation_started')[0]).toMatchObject({
      initiative_source: 'social', initiative_reason: LOOP, fallback_reason: 'continue_current_topic',
    });

    await play();
    expect(callsTo(DELIVERY_PATH)[0].body).toMatchObject({
      turn_id: `open-loop:${'a'.repeat(24)}:n0`,
      initiative_reason: LOOP,
      delivery_status: 'completed',
    });
  });

  it("keeps today's reason when the server has no open loop", async () => {
    startCall();

    await vi.advanceTimersByTimeAsync(2_000);
    expect(streamReasons()).toEqual(['continue_current_topic']);
  });

  it('says nothing on a skip, waits a cooldown, and does not raise a skipped open loop again this call', async () => {
    socialCandidate = LOOP;
    skip = true;
    startCall();

    await vi.advanceTimersByTimeAsync(2_000);
    expect(streamReasons()).toEqual([LOOP]);
    expect(callsTo(DELIVERY_PATH)).toHaveLength(0);
    expect(stages('initiative_skipped')).toEqual([expect.objectContaining({ initiative_source: 'social', initiative_reason: LOOP })]);

    // The skip spent the quiet period's prompt: nothing more until the person speaks.
    await vi.advanceTimersByTimeAsync(COOLDOWN_MS + 2_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(1);

    skip = false;
    userSpeaks();
    // The server still names the loop; the call has cooled it and falls back.
    await nextRemark(COOLDOWN_MS + 2_000);
    expect(streamReasons()).toEqual([LOOP, 'continue_current_topic']);
  });

  it('cools a reason the person did not answer, for the rest of the call', async () => {
    startCall({ max_idle_prompts: 3 });

    await vi.advanceTimersByTimeAsync(2_000);
    await play();
    expect(callsTo(DELIVERY_PATH)).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(INITIATIVE_ANSWER_WINDOW_MS + 1_000);
    expect(stages('initiative_ignored')).toEqual([
      expect.objectContaining({ initiative_reason: 'continue_current_topic', answer_window_ms: INITIATIVE_ANSWER_WINDOW_MS }),
    ]);
    userSpeaks();
    await vi.advanceTimersByTimeAsync(COOLDOWN_MS + 2_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(1);
    expect(stages('initiative_policy_decision').at(-1)).toMatchObject({ action: 'suppress', reason: 'reason_cooled' });

    // A new reason is not cooled.
    liveConversationStore.dispatch({ type: 'transcript_final', text: 'Do you think it will work?' });
    await vi.advanceTimersByTimeAsync(2_000);
    expect(streamReasons()).toEqual(['continue_current_topic', 'unresolved_question']);
  });

  it('keeps a reason the person answered, during or soon after the remark', async () => {
    startCall({ max_idle_prompts: 3 });

    await vi.advanceTimersByTimeAsync(2_000);
    await play({ answerWhilePlaying: true });
    expect(stages('initiative_answered')).toEqual([expect.objectContaining({ when: 'during' })]);

    await nextRemark(COOLDOWN_MS + 2_000);
    await vi.advanceTimersByTimeAsync(5_000);
    userSpeaks();
    expect(stages('initiative_answered').at(-1)).toMatchObject({ when: 'after' });
    expect(stages('initiative_ignored')).toHaveLength(0);

    await nextRemark(COOLDOWN_MS + 2_000);
    expect(streamReasons()).toEqual(['continue_current_topic', 'continue_current_topic', 'continue_current_topic']);
  });
});

describe('limits on social initiative in a quiet call', () => {
  it("stops social initiative when the person asks for quiet, while a task's report still comes", async () => {
    liveCallPresentationStore.update({ companionQuiet: true });
    startCall({}, true);

    await vi.advanceTimersByTimeAsync(5_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
    expect(stages('initiative_policy_decision').at(-1)).toMatchObject({ action: 'suppress', reason: 'call_quiet' });

    tasks = [{
      task_id: 'call-task:m1:0', ability: 'deep_research', query: 'flights to Lisbon', state: 'completed',
      asked_at: '2026-11-15T14:00:00Z', settled_at: '2026-11-15T14:01:00Z', result_message_id: 'r1', reported: false,
    }];
    reportCandidate = 'task_report:call-task:m1:0';
    await refreshLiveCallTasks();
    await nextRemark(12_000);
    expect(streamReasons()).toEqual(['task_report:call-task:m1:0']);
    // Delivered, the report is done; quiet still holds social initiative back.
    await vi.advanceTimersByTimeAsync(COOLDOWN_MS + 5_000);
    expect(streamReasons()).toEqual(['task_report:call-task:m1:0']);
    expect(stages('initiative_policy_decision').at(-1)).toMatchObject({ action: 'suppress', reason: 'call_quiet' });
  });

  it('holds social initiative back inside quiet hours', async () => {
    vi.setSystemTime(new Date(2026, 10, 15, 23, 30));
    startCall({ quiet_hours_enabled: true });

    await vi.advanceTimersByTimeAsync(5_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
    expect(stages('initiative_policy_decision').at(-1)).toMatchObject({ action: 'suppress', reason: 'quiet_hours' });
  });

  it('caps unprompted remarks per hour, across the quiet periods of a call', async () => {
    startCall({ max_idle_prompts: 3, max_initiatives_per_hour: 1 });

    await vi.advanceTimersByTimeAsync(2_000);
    await play({ answerWhilePlaying: true });
    await vi.advanceTimersByTimeAsync(COOLDOWN_MS + 2_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(1);
    expect(stages('initiative_policy_decision').at(-1)).toMatchObject({ action: 'suppress', reason: 'hourly_cap' });

    // Still capped just short of an hour after the remark; free once it is an hour old.
    await vi.advanceTimersByTimeAsync(60 * 60_000 - COOLDOWN_MS - 5_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(callsTo(STREAM_PATH)).toHaveLength(2);
  });

  it('writes what initiative did to the call log, and a repeated decision only when it changes', async () => {
    const record = vi.fn();
    liveVoiceCall.activeSession = { reporter: { record } } as unknown as LiveVoiceSession;
    startCall();

    await vi.advanceTimersByTimeAsync(2_000);
    await play();
    await vi.advanceTimersByTimeAsync(10_000);

    const logged = record.mock.calls.map(([event, details, source]) => ({ event, details, source }));
    expect(new Set(logged.map((entry) => entry.source))).toEqual(new Set(['live_conversation_initiative']));
    const decisions = logged
      .filter((entry) => entry.event === 'initiative_policy_decision')
      .map((entry) => `${entry.details.action}:${entry.details.reason}`);
    // Ticks every 750 ms, but no two neighbours are the same decision.
    expect(decisions.length).toBeGreaterThan(1);
    expect(decisions.every((decision, index) => index === 0 || decision !== decisions[index - 1])).toBe(true);
    expect(stages('initiative_policy_decision').length).toBeGreaterThan(decisions.length);
    expect(logged.map((entry) => entry.event)).toEqual(expect.arrayContaining([
      'initiative_generation_started', 'initiative_generation_completed', 'initiative_delivery_committed',
    ]));
  });
});
