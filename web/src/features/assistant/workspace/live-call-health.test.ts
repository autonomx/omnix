import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_CALL_START_FAILED_EVENT, ASSISTANT_LIVE_VOICE_STOP_EVENT } from '../../../events/bus';
import { resetFetchPipelineForTests } from '../../../api/fetchPipeline';
import {
  failureStatus,
  initializeLiveCallHealth,
  liveCallFailureMetrics,
  liveCallHealthSummary,
  liveCallRouteCheck,
  reportLiveCallFailure,
} from './live-call-health';
import { liveCallPresentationStore } from './live-call-presentation-store';

function answeredBy(node: string) {
  return async () => new Response('{}', { headers: { 'x-omnix-node': node } });
}

const CALL_HEADERS = { 'X-Omnix-Call-Id': 'chat-1' };

describe('live call health', () => {
  let dispose: () => void = () => undefined;

  beforeEach(() => {
    liveCallPresentationStore.resetForTests();
    dispose = initializeLiveCallHealth();
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_CALL_START_EVENT));
  });

  afterEach(() => {
    dispose();
    resetFetchPipelineForTests();
    document.cookie = 'omnix_call_affinity=; Path=/; Max-Age=0';
  });

  it('shows the first failure of a kind while the call runs and lists them all after it', () => {
    reportLiveCallFailure('speculation_accept', { status: 404 });
    expect(liveCallPresentationStore.getState().callHealth).toBe('Early reply accept failed (404).');
    // A repeat of the same kind leaves the line alone; a new kind's first failure takes it.
    liveCallPresentationStore.update({ callHealth: null });
    reportLiveCallFailure('speculation_accept', { status: 404 });
    expect(liveCallPresentationStore.getState().callHealth).toBeNull();
    reportLiveCallFailure('overlap_judgement');
    expect(liveCallPresentationStore.getState().callHealth).toBe('Interruption check failed.');

    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_STOP_EVENT));
    expect(liveCallPresentationStore.getState().callHealth)
      .toBe('Call problems: Early reply accept failed twice (404); Interruption check failed once.');

    // A failure after the call (its evaluation's save) joins the post-call line.
    reportLiveCallFailure('evaluation_save', { status: 422 });
    expect(liveCallHealthSummary()).toContain('Saving the call evaluation failed once (422)');
    // Anything else outside a call is not the call's (the podcast's portrait stream, a glance while typing).
    reportLiveCallFailure('avatar');
    reportLiveCallFailure('camera_glance', { status: 503 });
    expect(liveCallFailureMetrics().failure_avatar_count).toBe(0);
    expect(liveCallFailureMetrics().failure_camera_glance_count).toBe(0);
  });

  it('closes the call when its start failed, so later failures are not the call’s', () => {
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_CALL_START_FAILED_EVENT));
    reportLiveCallFailure('screen_glance', { status: 503 });
    expect(liveCallPresentationStore.getState().callHealth).toBeNull();
    expect(liveCallFailureMetrics().failure_count).toBe(0);
  });

  it('shows no call problems when no call has run', () => {
    dispose();
    liveCallPresentationStore.resetForTests();
    dispose = initializeLiveCallHealth();
    reportLiveCallFailure('avatar');
    reportLiveCallFailure('evaluation_save', { status: 500 });
    expect(liveCallPresentationStore.getState().callHealth).toBeNull();
    expect(liveCallFailureMetrics().failure_count).toBe(0);
  });

  it('counts every kind for the evaluation and starts each call clean', () => {
    reportLiveCallFailure('prewarm', { status: 503 });
    reportLiveCallFailure('greeting');
    const metrics = liveCallFailureMetrics();
    expect(metrics.failure_prewarm_count).toBe(1);
    expect(metrics.failure_greeting_count).toBe(1);
    expect(metrics.failure_avatar_count).toBe(0);
    expect(metrics.failure_count).toBe(2);
    expect(Object.keys(metrics).every((key) => /^failure_[a-z_]+$/.test(key))).toBe(true);

    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_CALL_START_EVENT));
    expect(liveCallFailureMetrics().failure_count).toBe(0);
    expect(liveCallPresentationStore.getState().callHealth).toBeNull();
  });

  it('flags a call whose call-bound requests reached two processes, once', async () => {
    const stream = '/api/live/speculation/sessions/chat-1/stream';
    const accept = '/api/live/speculation/sessions/chat-1/gen-1/accept';
    await liveCallRouteCheck(stream, { headers: CALL_HEADERS }, answeredBy('worker'));
    expect(liveCallFailureMetrics().failure_call_route_split_count).toBe(0);
    await liveCallRouteCheck(accept, { headers: CALL_HEADERS }, answeredBy('replica'));
    await liveCallRouteCheck(accept, { headers: CALL_HEADERS }, answeredBy('replica'));
    expect(liveCallFailureMetrics().failure_call_route_split_count).toBe(1);
  });

  it('checks only call-bound routes that name the call', async () => {
    // Not call-bound: a chat stream may go anywhere.
    await liveCallRouteCheck('/api/chat/sessions/chat-1/messages/stream', { headers: CALL_HEADERS }, answeredBy('a'));
    // Call-bound but without the call's header or cookie: the call's first prewarm warms the worker on purpose.
    await liveCallRouteCheck('/api/live-call/sessions/chat-1/prewarm', {}, answeredBy('b'));
    await liveCallRouteCheck('/api/live-call/sessions/chat-1/prewarm', { headers: CALL_HEADERS }, answeredBy('c'));
    expect(liveCallFailureMetrics().failure_call_route_split_count).toBe(0);

    document.cookie = 'omnix_call_affinity=chat-1; Path=/';
    await liveCallRouteCheck('http://localhost/api/live-call/sessions/chat-1/overlap-judgement', {}, answeredBy('d'));
    expect(liveCallFailureMetrics().failure_call_route_split_count).toBe(1);
  });

  it('reads the status a failed gateway call carries', () => {
    expect(failureStatus({ status: 404 })).toBe(404);
    expect(failureStatus(new Error('network'))).toBeNull();
    expect(failureStatus(null)).toBeNull();
  });
});
