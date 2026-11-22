import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LiveConversationProfile } from '../chat/liveConversationProfileClient';
import { ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, emitOmnixEvent } from '../../../events/bus';
import { resetCameraShareForTests, startCameraShare } from './camera-share';
import { companionInitiativeArbiter } from './companion-initiative-arbiter';
import { liveCallPresentationStore } from './live-call-presentation-store';
import { liveCallTasksStore } from './live-call-tasks-controller';
import { initializeLiveConversationInitiativeController } from './live-conversation-initiative-controller';
import { liveConversationStore } from './live-conversation-store';

const STREAM_PATH = '/api/chat/sessions/s1/live-call/greeting/stream';
const GLANCE_PATH = '/api/chat/sessions/s1/camera/glance';

type Call = { path: string; params: URLSearchParams };

let calls: Call[] = [];
let disposers: Array<() => void> = [];

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function idleProfile(): LiveConversationProfile {
  // Speaks up as soon as the call is quiet, and nothing in the transcript gives it a reason of its own.
  return {
    initiative_mode: 'proactive',
    idle_threshold_ms: 0,
    max_idle_prompts: 3,
    long_pause_behavior: 'wait',
    presence_preset: 'calm',
    conversation_stance: 'companion',
  } as unknown as LiveConversationProfile;
}

beforeEach(() => {
  calls = [];
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => {
        const track = { stop: vi.fn(), addEventListener: vi.fn() };
        return { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream;
      }),
    },
  });
  vi.spyOn(HTMLVideoElement.prototype, 'videoWidth', 'get').mockReturnValue(1280);
  vi.spyOn(HTMLVideoElement.prototype, 'videoHeight', 'get').mockReturnValue(720);
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: () => undefined } as never);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,AAAA');
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, window.location.origin);
    calls.push({ path: url.pathname, params: url.searchParams });
    if (url.pathname === GLANCE_PATH) return json({ status: 'started' });
    if (url.pathname === STREAM_PATH) {
      return new Response('data: {"type":"complete","content":"","metadata":{"generation_status":"skipped"}}\n\n', {
        status: 200, headers: { 'Content-Type': 'text/event-stream' },
      });
    }
    return json(null);
  }));
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  companionInitiativeArbiter.reset();
  resetCameraShareForTests();
});

afterEach(() => {
  disposers.forEach((dispose) => dispose());
  disposers = [];
  resetCameraShareForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  Reflect.deleteProperty(navigator, 'mediaDevices');
});

function startQuietCall(): void {
  liveCallPresentationStore.update({ autoSpeak: true });
  liveConversationStore.dispatch({ type: 'profile', profile: idleProfile() });
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  disposers.push(initializeLiveConversationInitiativeController());
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, { token: 1, timestamp: '2026-11-21T10:00:00Z' });
}

describe('an unprompted turn while the camera is shared', () => {
  it('glances first and tells the server the camera is shared', async () => {
    liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
    await startCameraShare();
    startQuietCall();

    await vi.waitFor(() => expect(calls.filter((call) => call.path === STREAM_PATH)).toHaveLength(1), { timeout: 4_000 });
    const glance = calls.findIndex((call) => call.path === GLANCE_PATH);
    const stream = calls.findIndex((call) => call.path === STREAM_PATH);
    expect(glance).toBeGreaterThanOrEqual(0);
    expect(glance).toBeLessThan(stream);
    expect(calls[stream].params.get('initiative_reason')).toBe('ambient_visual_presence');
    expect(calls[stream].params.get('camera_shared')).toBe('true');
  });

  it('without the share, a quiet call with nothing on screen has no reason to speak', async () => {
    startQuietCall();

    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(calls.filter((call) => call.path === STREAM_PATH || call.path === GLANCE_PATH)).toEqual([]);
  });
});
