import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CharacterAvatarPack, CharacterLiveCallRuntime } from '../characterClient';
import type { LiveVoicePcmSession } from '../../workspace/live-voice-pcm-session';
import { drawnAvatarPack, publishCharacterAvatarRuntime } from '../liveCharacterAvatarBridge';
import { LiveCallVisual } from '../LiveCallVisual';
import { fixture } from '../../../../test/fixture';
import { LivePortrait, livePortrait } from './livePortrait';

const CONTEXT_RATE = 48_000;

class FakeSocket {
  readyState = 1;
  binaryType = '';
  readonly sent: string[] = [];
  closed = false;
  private readonly listeners = new Map<string, Array<(event: unknown) => void>>();

  constructor(readonly url: string) {}

  addEventListener(type: string, listener: (event: unknown) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
    this.readyState = 3;
    this.emit('close', {});
  }

  emit(type: string, event: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  message(data: string | ArrayBuffer): void {
    this.emit('message', { data });
  }
}

type FakeImage = { id: number; close: () => void; closed: boolean };

function frameMessage(header: Record<string, unknown>, id: number): ArrayBuffer {
  const json = new TextEncoder().encode(JSON.stringify(header));
  const buffer = new ArrayBuffer(4 + json.length + 1);
  new DataView(buffer).setUint32(0, json.length, false);
  new Uint8Array(buffer, 4).set(json);
  new Uint8Array(buffer, 4 + json.length)[0] = id;
  return buffer;
}

function fakeSession(context: { currentTime: number }) {
  const audioContext = Object.assign(context, { sampleRate: CONTEXT_RATE, outputLatency: 0 });
  return {
    session: { audioContext, setPortraitClock: vi.fn() } as unknown as LiveVoicePcmSession,
    audioContext,
  };
}

function setup() {
  const sockets: FakeSocket[] = [];
  const images: FakeImage[] = [];
  const portrait = new LivePortrait(
    async (jpeg) => {
      const image: FakeImage = { id: jpeg[0], closed: false, close: () => { image.closed = true; } };
      images.push(image);
      return image as unknown as ImageBitmap;
    },
    (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    },
  );
  portrait.setPack({ renderer: 'portrait', fallback_renderer: 'sprite' });
  return { portrait, sockets, images };
}

const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  livePortrait.end();
  livePortrait.setPack(null);
  publishCharacterAvatarRuntime(null);
  vi.useRealTimers();
});

describe('the live portrait client', () => {
  it('is wanted only for a portrait pack', () => {
    const { portrait } = setup();
    expect(portrait.wanted()).toBe(true);
    portrait.setPack({ renderer: 'sprite' });
    expect(portrait.wanted()).toBe(false);
  });

  it('gives up when the TTS websocket sends no hello in time', () => {
    const { portrait } = setup();
    portrait.begin('chat:maya');
    expect(portrait.getSnapshot()).toMatchObject({ status: 'connecting', fallbackRenderer: 'sprite' });
    vi.advanceTimersByTime(1_000);
    expect(portrait.getSnapshot()).toMatchObject({ status: 'unavailable', reason: 'no_hello', fallbackRenderer: 'sprite' });
  });

  it('opens the avatar websocket with the hello token and becomes ready', () => {
    const { portrait, sockets } = setup();
    portrait.begin('chat:maya').onHello({ callKey: 'call-1', avatarToken: 'tok en' });
    vi.advanceTimersByTime(2_000);
    expect(sockets).toHaveLength(1);
    expect(sockets[0].url).toContain('/api/tts/live-call/avatar-websocket?token=tok%20en&session_id=chat%3Amaya');
    sockets[0].message(JSON.stringify({ type: 'ready', fallback_renderer: 'orb' }));
    expect(portrait.getSnapshot()).toEqual({ status: 'ready', fallbackRenderer: 'orb', reason: null });
  });

  it('draws the frame for what is heard and reports the play position in source samples', async () => {
    const { portrait, sockets, images } = setup();
    const context = { currentTime: 10 };
    const { session } = fakeSession(context);
    const hooks = portrait.begin('chat:maya');
    portrait.attachSession(session);
    expect(session.setPortraitClock).toHaveBeenCalledWith(true);
    hooks.onHello({ callKey: 'call-1', avatarToken: 'token' });
    hooks.onSegmentRate('seg-1', 24_000);
    const socket = sockets[0];
    socket.message(JSON.stringify({ type: 'ready' }));
    for (const [index, offset] of [0, 960, 1920].entries()) {
      socket.message(frameMessage({ output_id: 'turn-1', epoch: 1, segment_id: 'seg-1', offset }, index));
    }
    await flush();
    expect(portrait.currentFrame()).toBeNull();

    hooks.onWorkletEvent({ type: 'segment_started', segment_id: 'seg-1', audio_context_time_seconds: 10 });
    // 50 ms at 48 kHz is 1200 source samples at 24 kHz: the second frame (offset 960).
    hooks.onWorkletEvent({ type: 'portrait_clock', segment_id: 'seg-1', segment_played_samples: 2_400, audio_context_time_seconds: 10.05 });
    context.currentTime = 10.05;
    expect((portrait.currentFrame() as unknown as FakeImage).id).toBe(1);
    expect(images[0].closed).toBe(true);

    vi.advanceTimersByTime(250);
    expect(JSON.parse(socket.sent.at(-1) ?? '{}')).toEqual({ type: 'frame_ack', segment_id: 'seg-1', offset: 1_200 });
  });

  it('never draws a cancelled turn, even frames that arrive after the cancel', async () => {
    const { portrait, sockets } = setup();
    const context = { currentTime: 5 };
    const hooks = portrait.begin('chat:maya');
    portrait.attachSession(fakeSession(context).session);
    hooks.onHello({ callKey: 'call-1', avatarToken: 'token' });
    sockets[0].message(JSON.stringify({ type: 'ready' }));
    sockets[0].message(frameMessage({ output_id: 'turn-2', epoch: 2, segment_id: 'seg-a', offset: 0 }, 7));
    await flush();
    hooks.onWorkletEvent({ type: 'segment_started', segment_id: 'seg-a', audio_context_time_seconds: 5 });
    hooks.onWorkletEvent({ type: 'segment_cancelled', segment_id: 'seg-a', generation_epoch: 2, audio_context_time_seconds: 5 });
    sockets[0].message(frameMessage({ output_id: 'turn-2', epoch: 2, segment_id: 'seg-a', offset: 0 }, 8));
    await flush();
    hooks.onWorkletEvent({ type: 'segment_started', segment_id: 'seg-a', audio_context_time_seconds: 5.1 });
    context.currentTime = 5.2;
    expect(portrait.currentFrame()).toBeNull();
  });

  it('falls back when the service refuses or the stream is lost', () => {
    const { portrait, sockets } = setup();
    portrait.begin('chat:maya').onHello({ callKey: 'call-1', avatarToken: 'token' });
    sockets[0].message(JSON.stringify({ type: 'unavailable', code: 'portrait_busy' }));
    expect(portrait.getSnapshot()).toMatchObject({ status: 'unavailable', reason: 'portrait_busy' });

    portrait.begin('chat:maya').onHello({ callKey: 'call-2', avatarToken: 'token' });
    sockets[1].emit('close', {});
    expect(portrait.getSnapshot()).toMatchObject({ status: 'unavailable', reason: 'avatar_socket_refused' });

    portrait.begin('chat:maya').onHello({ callKey: 'call-3', avatarToken: 'token' });
    sockets[2].message(JSON.stringify({ type: 'ready' }));
    sockets[2].emit('close', {});
    expect(portrait.getSnapshot()).toMatchObject({ status: 'unavailable', reason: 'portrait_lost' });
  });

  it('ignores a previous call once it has ended', () => {
    const { portrait, sockets } = setup();
    const { session } = fakeSession({ currentTime: 0 });
    const old = portrait.begin('chat:maya');
    portrait.attachSession(session);
    old.onHello({ callKey: 'call-1', avatarToken: 'token' });
    portrait.end();
    expect(sockets[0].closed).toBe(true);
    expect(session.setPortraitClock).toHaveBeenLastCalledWith(false);
    expect(portrait.getSnapshot().status).toBe('off');
    old.onHello({ callKey: 'call-1', avatarToken: 'again' });
    vi.advanceTimersByTime(2_000);
    expect(sockets).toHaveLength(1);
    expect(portrait.getSnapshot().status).toBe('off');
  });
});

const portraitPack: CharacterAvatarPack = fixture({
  character_id: 'maya',
  version: 2,
  render_mode: 'audio_envelope',
  renderer: 'portrait',
  fallback_renderer: 'sprite',
  portrait_emotion: 'neutral',
  rig_asset_id: null,
  base_asset_id: 'image:maya-portrait',
  mouth_frames: {},
  blink_frames: {},
  expression_frames: {},
  outfit_frames: {},
  background_asset_ids: {},
  active_outfit: null,
  active_background: null,
  mouth_anchor: {},
  created_at: '2026-10-30T00:00:00Z',
  updated_at: '2026-10-30T00:00:00Z',
});

function portraitRuntime(pack: CharacterAvatarPack): CharacterLiveCallRuntime {
  return fixture({
    session_id: 'chat:maya',
    interaction_mode: 'character',
    display_name: 'Maya',
    character_id: 'maya',
    avatar_pack: pack,
  });
}

describe('the call visual for a portrait pack', () => {
  it('draws a portrait pack itself, or its fallback when the portrait is unavailable', () => {
    expect(drawnAvatarPack(portraitPack, false)).toBe(portraitPack);
    expect(drawnAvatarPack(portraitPack, true)?.renderer).toBe('sprite');
    expect(drawnAvatarPack({ ...portraitPack, fallback_renderer: 'orb' }, true)).toBeNull();
    const sprite = { ...portraitPack, renderer: 'sprite' as const };
    expect(drawnAvatarPack(sprite, true)).toBe(sprite);
  });

  it('shows the portrait image until frames arrive, then the pack fallback when unavailable', () => {
    vi.stubGlobal('requestAnimationFrame', () => 0);
    vi.stubGlobal('cancelAnimationFrame', () => undefined);
    act(() => publishCharacterAvatarRuntime(portraitRuntime(portraitPack)));
    livePortrait.setPack(portraitPack);
    const view = render(<LiveCallVisual voiceMode="idle" thinking={false} />);
    const figure = view.container.querySelector('figure');
    expect(figure?.dataset.renderer).toBe('portrait');
    expect(view.getByAltText('Maya live portrait').getAttribute('src')).toBe('/api/assets/image%3Amaya-portrait/file');

    act(() => {
      livePortrait.begin('chat:maya');
      vi.advanceTimersByTime(1_000);
    });
    expect(view.container.querySelector('figure')?.dataset.renderer).toBe('sprite');
    expect(view.getByAltText('Maya live avatar').getAttribute('src')).toBe('/api/assets/image%3Amaya-portrait/file');
    vi.unstubAllGlobals();
  });

  it('shows the orb when an unavailable portrait falls back to it', () => {
    const pack = { ...portraitPack, fallback_renderer: 'orb' as const };
    act(() => publishCharacterAvatarRuntime(portraitRuntime(pack)));
    livePortrait.setPack(pack);
    act(() => {
      livePortrait.begin('chat:maya');
      vi.advanceTimersByTime(1_000);
    });
    const view = render(<LiveCallVisual voiceMode="idle" thinking={false} />);
    expect(view.container.querySelector('figure')).toBeNull();
    expect(view.container.querySelector('[data-has-character-avatar]')).toBeNull();
  });
});
