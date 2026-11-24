import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT } from '../../../events/bus';
import { sendChatWithAssistantContext, type AssistantChatRoute } from './assistant-context-chat';
import { assistantContextStore, type DesktopShareSession } from './assistant-context-store';
import { liveConversationStore } from './live-conversation-store';
import {
  glanceScreenShare,
  initializeLiveCallScreenShare,
  resetLiveCallScreenShareForTests,
  screenShareTurnFields,
} from './live-call-screen-share';

let glanceStatus = 'started';
let glances: Array<{ path: string; body: unknown }> = [];
let buildPayload: ReturnType<typeof vi.fn>;
let dispose: () => void = () => undefined;

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function shareScreen(): void {
  buildPayload = vi.fn(async () => ({ currentImageDataUrl: 'data:image/jpeg;base64,FRAME', captureMode: 'single', historyTimestamps: [] }));
  const track = { stop: vi.fn(), addEventListener: vi.fn() };
  const share = {
    stream: { getTracks: () => [track], getVideoTracks: () => [track] },
    video: document.createElement('video'),
    capture: { buildPayload, stop: vi.fn() },
    sourceFingerprint: 'screen-1',
  } as unknown as DesktopShareSession;
  assistantContextStore.update({ desktopShare: share, desktopStatus: 'Buffering recent frames' });
}

function recordingSender() {
  const calls: Array<{ route: AssistantChatRoute; body: Record<string, unknown> }> = [];
  const send = (route: AssistantChatRoute, body: Record<string, unknown>) => {
    calls.push({ route, body });
    return Promise.resolve(route);
  };
  return { calls, send };
}

beforeEach(() => {
  glances = [];
  glanceStatus = 'started';
  vi.spyOn(HTMLVideoElement.prototype, 'videoWidth', 'get').mockReturnValue(2560);
  vi.spyOn(HTMLVideoElement.prototype, 'videoHeight', 'get').mockReturnValue(1440);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: () => undefined } as never);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,AAAA');
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(new URL(String(input), window.location.origin), init);
    const path = new URL(request.url).pathname;
    if (path.endsWith('/screen/glance')) {
      glances.push({ path, body: await request.json() });
      return json({ status: glanceStatus });
    }
    return json(null);
  }));
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  resetLiveCallScreenShareForTests();
  dispose = initializeLiveCallScreenShare();
});

afterEach(() => {
  dispose();
  liveConversationStore.reset();
  assistantContextStore.resetForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('the shared screen in a call (D2)', () => {
  it('glances when the person starts speaking, and not without a shared screen', async () => {
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT));
    await settle();
    expect(glances).toEqual([]);

    shareScreen();
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT));
    window.dispatchEvent(new Event(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT));
    await settle();

    expect(glances).toEqual([{ path: '/api/chat/sessions/s1/screen/glance', body: { image: 'data:image/jpeg;base64,AAAA' } }]);
  });

  it('a call turn says screen_shared on the chat route and sends no frames; a typed turn still sends them', async () => {
    shareScreen();
    const { calls, send } = recordingSender();

    await expect(sendChatWithAssistantContext('s1', { content: 'what do you think?' }, send, { liveCallTurn: true }))
      .resolves.toBe('chat');
    expect(calls[0].body).toEqual({ content: 'what do you think?', screen_shared: true });
    expect(glances).toHaveLength(1);
    expect(buildPayload).not.toHaveBeenCalled();

    await expect(sendChatWithAssistantContext('s1', { content: 'and this?' }, send)).resolves.toBe('context');
    expect(calls[1].body).toMatchObject({ content: 'and this?', desktop_current_image_data_url: 'data:image/jpeg;base64,FRAME' });
    expect(calls[1].body).not.toHaveProperty('screen_shared');
  });

  it('stops sharing and says why when the call cannot see the screen', async () => {
    glanceStatus = 'remote_vision_not_allowed';
    shareScreen();

    expect(await screenShareTurnFields('s1')).toEqual({});

    const state = assistantContextStore.getState();
    expect(state.desktopShare).toBeNull();
    expect(state.desktopStatus).toContain('allow remote vision');
  });

  it('leaves a newer share alone when an older share\'s glance answers that it cannot be seen', async () => {
    glanceStatus = 'vision_unavailable';
    shareScreen();
    const glance = glanceScreenShare('s1');
    shareScreen();  // shared again while the first answer is on its way
    const newer = assistantContextStore.getState().desktopShare;

    await expect(glance).resolves.toBe(false);
    expect(assistantContextStore.getState().desktopShare).toBe(newer);
  });
});
