import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT } from '../../../events/bus';
import { sendChatWithAssistantContext } from './assistant-context-chat';
import { assistantContextStore } from './assistant-context-store';
import {
  cameraShareState,
  cameraShareTurnFields,
  glanceCameraShare,
  glanceOnTyping,
  resetCameraShareForTests,
  startCameraShare,
  stopCameraShare,
  toggleCameraShare,
} from './camera-share';
import { liveConversationStore } from './live-conversation-store';

type FakeTrack = { stop: ReturnType<typeof vi.fn>; addEventListener: ReturnType<typeof vi.fn> };

let tracks: FakeTrack[] = [];
let getUserMedia: ReturnType<typeof vi.fn>;
let glanceStatus = 'started';
let glances: Array<{ path: string; body: unknown }> = [];

function fakeStream(): MediaStream {
  const track = { stop: vi.fn(), addEventListener: vi.fn() };
  tracks.push(track);
  return { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream;
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  tracks = [];
  glances = [];
  glanceStatus = 'started';
  getUserMedia = vi.fn(async () => fakeStream());
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
  vi.spyOn(HTMLVideoElement.prototype, 'videoWidth', 'get').mockReturnValue(1280);
  vi.spyOn(HTMLVideoElement.prototype, 'videoHeight', 'get').mockReturnValue(720);
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: () => undefined } as never);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,AAAA');
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(new URL(String(input), window.location.origin), init);
    const path = new URL(request.url).pathname;
    if (path.endsWith('/camera/glance')) {
      glances.push({ path, body: await request.json() });
      return json({ status: glanceStatus });
    }
    return json(null);
  }));
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  resetCameraShareForTests();
});

afterEach(() => {
  resetCameraShareForTests();
  liveConversationStore.reset();
  assistantContextStore.resetForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'mediaDevices');
});

describe('the shared camera', () => {
  it('opens only the front camera, video only, and stays on until it is turned off', async () => {
    await toggleCameraShare();

    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    expect(cameraShareState().phase).toBe('on');
    expect(cameraShareState().stream).not.toBeNull();

    await toggleCameraShare();

    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(cameraShareState()).toMatchObject({ phase: 'off', stream: null });
  });

  it('a refused camera is an error, not a share', async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException('no', 'NotAllowedError'));

    await startCameraShare();

    expect(cameraShareState()).toMatchObject({ phase: 'error', error: 'Camera access was not allowed.' });
  });

  it('glances when the person starts speaking, at most every few seconds', async () => {
    await startCameraShare();

    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT));
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT));
    await settle();

    expect(glances).toEqual([{ path: '/api/chat/sessions/s1/camera/glance', body: { image: 'data:image/jpeg;base64,AAAA' } }]);
  });

  it('glances as a call starts, so its greeting and first turn know what the camera shows', async () => {
    await startCameraShare();

    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_CALL_START_EVENT));
    await settle();

    expect(glances).toEqual([{ path: '/api/chat/sessions/s1/camera/glance', body: { image: 'data:image/jpeg;base64,AAAA' } }]);
  });

  it('glances on typing, and not at all once the camera is off', async () => {
    await startCameraShare();
    glanceOnTyping();
    await settle();
    stopCameraShare();

    glanceOnTyping();
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT));
    await settle();

    expect(glances).toHaveLength(1);
  });

  it('a turn says the camera is shared and carries no picture; a chat without a recent glance glances first', async () => {
    await startCameraShare();
    const bodies: Array<Record<string, unknown>> = [];

    await sendChatWithAssistantContext('s1', { content: 'can you see me?' }, (_route, body) => {
      bodies.push(body);
      return Promise.resolve(null);
    });

    expect(glances).toHaveLength(1);
    expect(bodies).toEqual([{ content: 'can you see me?', camera_shared: true }]);
  });

  it('a turn without the share adds nothing', async () => {
    expect(await cameraShareTurnFields('s1')).toEqual({});
  });

  it('turns itself off with a reason when the assistant cannot see the camera', async () => {
    glanceStatus = 'remote_vision_not_allowed';
    await startCameraShare();

    expect(await cameraShareTurnFields('s1')).toEqual({});
    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(cameraShareState()).toMatchObject({ phase: 'error', stream: null });
    expect(cameraShareState().error).toContain('allow remote vision');
  });

  it('a late "cannot see" answer leaves a camera turned on again alone', async () => {
    glanceStatus = 'vision_unavailable';
    await startCameraShare();
    const glance = glanceCameraShare('s1');
    stopCameraShare();
    await startCameraShare();  // turned on again while the first answer is on its way

    await expect(glance).resolves.toBe(false);
    expect(cameraShareState().phase).toBe('on');
    expect(tracks[1].stop).not.toHaveBeenCalled();
  });
});
