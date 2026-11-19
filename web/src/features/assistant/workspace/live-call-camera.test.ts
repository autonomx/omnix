import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { sendChatWithAssistantContext, type AssistantChatRoute } from './assistant-context-chat';
import { assistantContextStore } from './assistant-context-store';
import {
  closeLiveCallCamera,
  LIVE_CALL_CAMERA_LONGEST_SIDE,
  liveCallCameraState,
  noteLiveCallCameraRequest,
  openLiveCallCamera,
  refreshLiveCallCameraAvailability,
  resetLiveCallCamera,
  resetLiveCallCameraForTests,
  takeLiveCallCameraFrame,
  takeLiveCallCameraPicture,
} from './live-call-camera';
import { speculationRequestCanReuse } from './live-speculation-controller';

type FakeTrack = { stop: ReturnType<typeof vi.fn> };

let tracks: FakeTrack[] = [];
let getUserMedia: ReturnType<typeof vi.fn>;
let available = true;
let drawn: Array<[number, number]> = [];

function fakeStream(): MediaStream {
  const track = { stop: vi.fn() };
  tracks.push(track);
  return { getTracks: () => [track] } as unknown as MediaStream;
}

function video(width = 1920, height = 1080): HTMLVideoElement {
  const element = document.createElement('video');
  Object.defineProperty(element, 'videoWidth', { value: width });
  Object.defineProperty(element, 'videoHeight', { value: height });
  return element;
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  tracks = [];
  drawn = [];
  available = true;
  getUserMedia = vi.fn(async () => fakeStream());
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (this: HTMLCanvasElement) {
    return { drawImage: () => drawn.push([this.width, this.height]) } as never;
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,AAAA');
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    if (path === '/api/chat/sessions/s1/live-call/camera') {
      return json({ available, remote: false, reason: available ? 'ready' : 'vision_not_configured' });
    }
    return json(null);
  }));
  resetLiveCallCameraForTests();
});

afterEach(() => {
  resetLiveCallCameraForTests();
  assistantContextStore.resetForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'mediaDevices');
});

describe('the call camera', () => {
  it('opens only the front camera, video only, and shows the preview', async () => {
    await openLiveCallCamera();

    expect(getUserMedia).toHaveBeenCalledWith({ video: { facingMode: 'user' }, audio: false });
    expect(liveCallCameraState().phase).toBe('preview');
    expect(liveCallCameraState().stream).not.toBeNull();
  });

  it('takes one scaled JPEG frame and stops the camera at once', async () => {
    await openLiveCallCamera();

    expect(takeLiveCallCameraPicture(video())).toBe(true);

    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(drawn).toEqual([[LIVE_CALL_CAMERA_LONGEST_SIDE, 576]]);
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledWith('image/jpeg', 0.85);
    expect(liveCallCameraState()).toMatchObject({ phase: 'attached', stream: null });
  });

  it('sends the picture with one turn only', async () => {
    await openLiveCallCamera();
    takeLiveCallCameraPicture(video(640, 480));

    expect(takeLiveCallCameraFrame()).toBe('data:image/jpeg;base64,AAAA');
    expect(takeLiveCallCameraFrame()).toBeNull();
    expect(liveCallCameraState().phase).toBe('off');
  });

  it('closing the preview stops the camera and keeps no picture', async () => {
    await openLiveCallCamera();
    closeLiveCallCamera();

    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(liveCallCameraState().phase).toBe('off');
    expect(takeLiveCallCameraFrame()).toBeNull();
  });

  it('stops a camera that opens after its preview was closed', async () => {
    let resolve: (stream: MediaStream) => void = () => undefined;
    getUserMedia.mockImplementation(() => new Promise<MediaStream>((done) => { resolve = done; }));
    const opening = openLiveCallCamera();
    expect(liveCallCameraState().phase).toBe('opening');

    closeLiveCallCamera();
    resolve(fakeStream());
    await opening;

    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(liveCallCameraState()).toMatchObject({ phase: 'off', stream: null });
  });

  it('says so when the camera is refused', async () => {
    getUserMedia.mockRejectedValue(new DOMException('denied', 'NotAllowedError'));

    await openLiveCallCamera();

    expect(liveCallCameraState()).toMatchObject({ phase: 'error', error: 'Camera access was not allowed.' });
  });

  it('a picture that could not be taken is an error, and the camera still stops', async () => {
    await openLiveCallCamera();

    expect(takeLiveCallCameraPicture(video(0, 0))).toBe(false);

    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(liveCallCameraState().phase).toBe('error');
    expect(takeLiveCallCameraFrame()).toBeNull();
  });

  it('a call asking to see something opens nothing', async () => {
    await refreshLiveCallCameraAvailability('s1');

    noteLiveCallCameraRequest('the label on the jar');

    expect(liveCallCameraState().requested).toBe('the label on the jar');
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('a request is ignored when the call cannot see', async () => {
    available = false;
    await refreshLiveCallCameraAvailability('s1');

    noteLiveCallCameraRequest('the jar');

    expect(liveCallCameraState()).toMatchObject({ available: false, availabilitySessionId: 's1', requested: null });
  });

  it('losing availability closes an open camera', async () => {
    await refreshLiveCallCameraAvailability('s1');
    await openLiveCallCamera();
    available = false;

    await refreshLiveCallCameraAvailability('s1');

    expect(tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(liveCallCameraState().phase).toBe('off');
  });

  it('a call starting or ending drops the camera, the picture and the request', async () => {
    await refreshLiveCallCameraAvailability('s1');
    noteLiveCallCameraRequest('the jar');
    await openLiveCallCamera();
    takeLiveCallCameraPicture(video());

    resetLiveCallCamera();

    expect(liveCallCameraState()).toMatchObject({ phase: 'off', requested: null });
    expect(takeLiveCallCameraFrame()).toBeNull();
  });
});

describe('a turn with a camera picture', () => {
  it('goes to the chat route even in agent mode', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 200 })));
    assistantContextStore.update({ agentMode: true });
    const calls: AssistantChatRoute[] = [];
    const send = (route: AssistantChatRoute) => {
      calls.push(route);
      return Promise.resolve(route);
    };

    await sendChatWithAssistantContext('s1', { content: 'what is this?', camera_image: 'data:image/jpeg;base64,AA' }, send,
      { liveCallTurn: true });
    await sendChatWithAssistantContext('s1', { content: 'and now?' }, send, { liveCallTurn: true });

    expect(calls).toEqual(['chat', 'context']);
  });

  it('is never answered by a speculative reply', () => {
    expect(speculationRequestCanReuse({ content: 'what is this?' }, null, null)).toBe(true);
    expect(speculationRequestCanReuse({ content: 'what is this?', camera_image: 'data:image/jpeg;base64,AA' }, null, null))
      .toBe(false);
  });
});
