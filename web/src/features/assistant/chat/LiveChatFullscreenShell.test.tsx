 
/* eslint-disable no-restricted-syntax -- baseline WP-9.x */
import { act, cleanup, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { liveCallPresentationStore } from '../workspace/live-call-presentation-store';
import { callSceneStore, loadCallScene } from '../workspace/live-call-scene';
import { liveConversationStore } from '../workspace/live-conversation-store';
import { LiveChatFullscreenShell, type LiveChatMessage } from './LiveChatFullscreenShell';
import type { CharacterLiveCallRuntime } from './characterClient';
import { publishCharacterAvatarRuntime } from './liveCharacterAvatarBridge';
import { livePortrait, portraitNotice, requestLiveVideo, resetLiveVideoRequests } from './portrait/livePortrait';
import { packRevision, rememberMemberLoop, resetMemberLoops } from './portrait/memberIdleLoops';
import { useDrawnAvatarPack } from './portrait/useDrawnAvatarPack';
import { fixture } from '../../../test/fixture';
import { createTestQueryClient, TestProviders } from '../../../test/renderWithProviders';

const sockets: unknown[] = [];
vi.stubGlobal('WebSocket', class {
  static OPEN = 1;
  readyState = 1;
  binaryType = '';
  private readonly listeners = new Map<string, ((event: unknown) => void)[]>();
  constructor() { sockets.push(this); }
  addEventListener(type: string, listener: (event: unknown) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  emit(type: string, event: unknown): void { for (const listener of this.listeners.get(type) ?? []) listener(event); }
  send(): void { /* nothing to send to */ }
  close(): void { this.readyState = 3; }
});

const mayaRuntime: CharacterLiveCallRuntime = fixture({
  session_id: 'chat:maya',
  interaction_mode: 'character',
  display_name: 'Maya',
  character_id: 'maya',
  avatar_pack: {
    character_id: 'maya',
    version: 1,
    render_mode: 'audio_envelope',
    renderer: 'sprite',
    rig_asset_id: null,
    base_asset_id: 'image:maya-base',
    mouth_frames: { closed: 'image:maya-closed' },
    blink_frames: {},
    expression_frames: {},
    outfit_frames: {},
    background_asset_ids: {},
  },
});
import {
  enterLiveChatFullscreen,
  exitLiveChatFullscreen,
  initializeLiveChatFullscreenController,
  resetLiveChatFullscreenStateForTests,
} from './live-chat-fullscreen-controller';

const sourceCallClick = vi.fn();
const sourceSubmit = vi.fn((text: string) => Boolean(text.trim()));
const messages: LiveChatMessage[] = [
  { id: 'a1', role: 'assistant', text: 'Welcome to our corner of the stars.', timestamp: null },
  { id: 'u1', role: 'user', text: 'Can you tell me a story?', timestamp: null },
];

function renderShell() {
  return render(
    <TestProviders queryClient={createTestQueryClient()}>
      <LiveChatFullscreenShell messages={messages} onSendMessage={sourceSubmit} onToggleCall={sourceCallClick} />
    </TestProviders>,
  );
}

describe('LiveChatFullscreenShell', () => {
  let dispose: () => void;

  it('draws a live portrait on the stage, and the pack\'s fallback with the reason when it cannot show', async () => {
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 1);
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
    resetLiveChatFullscreenStateForTests();
    const disposeFullscreen = initializeLiveChatFullscreenController();
    const pack = { ...mayaRuntime.avatar_pack, renderer: 'portrait', fallback_renderer: 'sprite', base_asset_id: 'image:maya-portrait' } as CharacterLiveCallRuntime['avatar_pack'];
    const portraitRuntime = { ...mayaRuntime, avatar_pack: pack };
    act(() => {
      publishCharacterAvatarRuntime(portraitRuntime);
      livePortrait.setPack(pack);
    });
    renderShell();
    await act(async () => { await enterLiveChatFullscreen(); });

    const stage = screen.getByRole('region', { name: 'Maya character stage' });
    expect(stage.querySelector('figure')?.dataset.renderer).toBe('portrait');
    expect(within(stage).getByAltText('Maya live portrait').getAttribute('src')).toBe('/api/assets/image%3Amaya-portrait/file');
    expect(stage.querySelector('canvas')).not.toBeNull();
    expect(within(stage).getByText('Live portrait linked')).toBeTruthy();
    expect(within(stage).queryByLabelText('Maya visual placeholder')).toBeNull();

    // The portrait cannot show: the pack's image, and why.
    act(() => {
      const hooks = livePortrait.begin('chat:maya');
      hooks.onHello({ callKey: 'call', avatarToken: 'token' });
    });
    const socket = sockets.at(-1) as { emit: (type: string, event: unknown) => void };
    act(() => socket.emit('message', { data: JSON.stringify({ type: 'unavailable', code: 'model_missing' }) }));
    expect(stage.querySelector('canvas')).toBeNull();
    expect(within(stage).getByAltText('Maya live avatar').getAttribute('src')).toBe('/api/assets/image%3Amaya-closed/file');
    expect(within(stage).getByRole('status').textContent).toContain('models are not installed');

    act(() => {
      livePortrait.end();
      livePortrait.setPack(null);
    });
    await act(async () => { await exitLiveChatFullscreen(); });
    disposeFullscreen();
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    sourceCallClick.mockClear();
    sourceSubmit.mockClear();
    Object.defineProperty(document.documentElement, 'requestFullscreen', { configurable: true, value: undefined });
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    resetLiveChatFullscreenStateForTests();
    dispose = initializeLiveChatFullscreenController();
    liveConversationStore.reset();
    liveConversationStore.dispatch({ type: 'identity', identity: { characterId: 'maya', displayName: 'Maya' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'delivery', value: 'audio_started' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'floor_owner', value: 'assistant' } });
    liveConversationStore.dispatch({ type: 'duplex', duplex: { resolvedMode: 'echo_aware', reason: 'calibration_confident' } });
  });

  afterEach(async () => {
    publishCharacterAvatarRuntime(null);
    await exitLiveChatFullscreen();
    dispose();
    cleanup();
    liveConversationStore.reset();
    resetLiveVideoRequests();
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('renders a character-first stage and the conversation it is given', () => {
    enterLiveChatFullscreen('header');
    renderShell();
    act(() => publishCharacterAvatarRuntime(mayaRuntime));

    const dialog = screen.getByRole('dialog', { name: 'Immersive Live Chat with Maya' });
    const fullscreen = within(dialog);
    expect(dialog).toBeInTheDocument();
    expect(fullscreen.getByAltText('Maya live avatar')).toBeInTheDocument();
    expect(fullscreen.getByText('Welcome to our corner of the stars.')).toBeInTheDocument();
    expect(fullscreen.getByText('Can you tell me a story?')).toBeInTheDocument();
    expect(fullscreen.getByText('Maya is speaking')).toBeInTheDocument();
    expect(fullscreen.getByText(/Microphone listening · Echo-aware/)).toBeInTheDocument();
  });

  it('gives everyone on the call a tile, and outlines the one speaking', async () => {
    const leoPack = { ...mayaRuntime.avatar_pack, character_id: 'leo', base_asset_id: 'image:leo-base', mouth_frames: { closed: 'image:leo-closed' } };
    const withGuest = fixture<CharacterLiveCallRuntime>({
      ...mayaRuntime,
      scene_guests: [{ character_id: 'leo', display_name: 'Leo', voice_asset_id: null, voice_speaker_id: null, speech_style: null, avatar_pack: leoPack }],
    });
    const members = [
      { character_id: 'maya', display_name: 'Maya', role: 'host', seat: 0 },
      { character_id: 'leo', display_name: 'Leo', role: 'guest', seat: 1 },
      // A guest the runtime has not been read for yet shows its initial.
      { character_id: 'ivy', display_name: 'Ivy', role: 'guest', seat: 2 },
    ];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const body = new URL(raw, window.location.origin).pathname.endsWith('/scene')
        ? { available: true, reason: 'ready', max_guests: 2, members }
        : { detail: 'not_found' };
      return new Response(JSON.stringify(body), { status: 'members' in body ? 200 : 404, headers: { 'Content-Type': 'application/json' } });
    });
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:maya' });
    liveCallPresentationStore.update({ speaking: true, sceneSpeakerId: null });
    enterLiveChatFullscreen('header');
    renderShell();
    act(() => publishCharacterAvatarRuntime(withGuest));
    await act(async () => { await loadCallScene('chat:maya'); });

    const room = await screen.findByRole('list', { name: 'Call members' });
    const tiles = within(room).getAllByRole('listitem');
    expect(tiles.map((tile) => tile.dataset.role)).toEqual(['host', 'guest', 'guest']);
    expect(within(tiles[0]).getByAltText('Maya live avatar')).toBeTruthy();
    expect(within(tiles[1]).getByAltText('Leo avatar').getAttribute('src')).toBe('/api/assets/image%3Aleo-closed/file');
    expect(within(tiles[2]).getByLabelText('Ivy visual placeholder')).toBeTruthy();
    expect(tiles.map((tile) => tile.dataset.speaking ?? '')).toEqual(['true', '', '']);

    // A guest's line: its tile is outlined, and the host's mouth stays shut.
    act(() => liveCallPresentationStore.update({ sceneSpeakerId: 'leo' }));
    expect(tiles.map((tile) => tile.dataset.speaking ?? '')).toEqual(['', 'true', '']);
    expect(within(tiles[1]).getByText('· speaking')).toBeTruthy();
    expect(tiles[0].querySelector('.live-chat-stage-avatar')?.getAttribute('data-mouth-frame')).toBe('closed');

    act(() => {
      liveCallPresentationStore.resetForTests();
      callSceneStore.resetForTests();
    });
    // Without guests the stage is the single character again.
    expect(screen.queryByRole('list', { name: 'Call members' })).toBeNull();
  });

  it("keeps every portrait member live: the speaker's face streams, and the others play their idle loops", async () => {
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => 'blob:leo-idle');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const portraitPack = (id: string) => ({ ...mayaRuntime.avatar_pack, character_id: id, renderer: 'portrait',
      fallback_renderer: 'sprite', base_asset_id: `image:${id}-portrait` }) as CharacterLiveCallRuntime['avatar_pack'];
    const leoPack = portraitPack('leo');
    const withGuest = fixture<CharacterLiveCallRuntime>({
      ...mayaRuntime,
      avatar_pack: portraitPack('maya'),
      scene_guests: [{ character_id: 'leo', display_name: 'Leo', voice_asset_id: null, voice_speaker_id: null, speech_style: null, avatar_pack: leoPack }],
    });
    const members = [
      { character_id: 'maya', display_name: 'Maya', role: 'host', seat: 0 },
      { character_id: 'leo', display_name: 'Leo', role: 'guest', seat: 1 },
    ];
    const idleAsked: (string | null)[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const url = new URL(raw, window.location.origin);
      let body: Record<string, unknown> = { detail: 'not_found' };
      if (url.pathname.endsWith('/scene')) body = { available: true, reason: 'ready', max_guests: 2, members };
      if (url.pathname === '/api/tts/live-call/portrait-idle') {
        const speaker = url.searchParams.get('speaker_id');
        idleAsked.push(speaker);
        body = speaker === 'leo' ? { ok: true, frame_ms: 80, idle: [btoa('x')], blink: [] } : { ok: false, code: 'portrait_busy' };
      }
      return new Response(JSON.stringify(body), { status: 'detail' in body ? 404 : 200, headers: { 'Content-Type': 'application/json' } });
    });
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:maya' });
    requestLiveVideo('chat:maya'); // "Load live video" was pressed in this chat
    enterLiveChatFullscreen('header');
    renderShell();
    act(() => {
      publishCharacterAvatarRuntime(withGuest);
      livePortrait.setPack(withGuest.avatar_pack);
    });
    await act(async () => { await loadCallScene('chat:maya'); });

    const room = await screen.findByRole('list', { name: 'Call members' });
    const tiles = within(room).getAllByRole('listitem');
    await screen.findByAltText('Leo avatar');
    expect(idleAsked).toEqual(expect.arrayContaining([null, 'leo'])); // the host names no speaker
    await act(async () => { await Promise.resolve(); });
    // The host's own portrait is the live one; Leo idles on his own loop, never on Maya's stream.
    expect(tiles[0].querySelector('canvas')).not.toBeNull();
    expect(tiles[1].querySelector('canvas')).toBeNull();
    expect(within(tiles[1]).getByAltText('Leo avatar').getAttribute('src')).toBe('blob:leo-idle');

    // Leo's turn: his face streams in his tile (his loop until the first frame), and Maya's leaves the stream.
    act(() => { livePortrait.begin('chat:maya', { id: 'leo', pack: leoPack }); });
    expect(tiles[1].querySelector('canvas')).not.toBeNull();
    expect(within(tiles[1]).getByAltText('Leo avatar').getAttribute('data-portrait-idle')).toBe('true');
    expect(tiles[0].querySelector('canvas')).toBeNull();
    expect(within(tiles[0]).getByAltText('Maya live portrait').getAttribute('src')).toBe('/api/assets/image%3Amaya-portrait/file');

    // Leo's portrait cannot keep up: his fallback is only his picture, so he idles on his loop rather than swapping
    // to the uncropped still (the tile resizing and going still each time, 2026-11-21).
    act(() => {
      const hooks = livePortrait.begin('chat:maya', { id: 'leo', pack: leoPack });
      hooks.onHello({ callKey: 'call', avatarToken: 'token' });
    });
    const socket = sockets.at(-1) as { emit: (type: string, event: unknown) => void };
    act(() => socket.emit('message', { data: JSON.stringify({ type: 'unavailable', code: 'portrait_busy' }) }));
    expect(livePortrait.getSnapshot()).toMatchObject({ status: 'unavailable', speakerId: 'leo' });
    expect(tiles[1].querySelector('canvas')).toBeNull();
    expect(tiles[1].querySelector('.live-chat-stage-tile-picture')?.getAttribute('data-renderer')).toBe('portrait');
    expect(within(tiles[1]).getByAltText('Leo avatar').getAttribute('src')).toBe('blob:leo-idle');

    act(() => {
      livePortrait.end();
      livePortrait.setPack(null);
      liveCallPresentationStore.resetForTests();
      callSceneStore.resetForTests();
      resetMemberLoops();
    });
  });

  it('keeps a voice-only call still until live video is asked for, and offers it on the call card', async () => {
    const portraitPack = (id: string) => ({ ...mayaRuntime.avatar_pack, character_id: id, renderer: 'portrait',
      fallback_renderer: 'sprite', base_asset_id: `image:${id}-portrait` }) as CharacterLiveCallRuntime['avatar_pack'];
    const withGuest = fixture<CharacterLiveCallRuntime>({
      ...mayaRuntime,
      avatar_pack: portraitPack('maya'),
      scene_guests: [{ character_id: 'leo', display_name: 'Leo', voice_asset_id: null, voice_speaker_id: null, speech_style: null, avatar_pack: portraitPack('leo') }],
    });
    const members = [
      { character_id: 'maya', display_name: 'Maya', role: 'host', seat: 0 },
      { character_id: 'leo', display_name: 'Leo', role: 'guest', seat: 1 },
    ];
    const idleAsked: (string | null)[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const url = new URL(raw, window.location.origin);
      let body: Record<string, unknown> = { detail: 'not_found' };
      if (url.pathname.endsWith('/scene')) body = { available: true, reason: 'ready', max_guests: 2, members };
      if (url.pathname === '/api/tts/live-call/portrait-idle') idleAsked.push(url.searchParams.get('speaker_id'));
      return new Response(JSON.stringify(body), { status: 'detail' in body ? 404 : 200, headers: { 'Content-Type': 'application/json' } });
    });
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:maya' });
    enterLiveChatFullscreen('header');
    renderShell();
    act(() => publishCharacterAvatarRuntime(withGuest));
    await act(async () => { await loadCallScene('chat:maya'); });

    await screen.findByRole('list', { name: 'Call members' });
    const dialog = screen.getByRole('dialog', { name: 'Immersive Live Chat with Maya' });
    expect(await within(dialog).findByRole('button', { name: 'Load live video' })).toBeEnabled();
    await act(async () => { await Promise.resolve(); });
    expect(idleAsked).toEqual([]); // no idle loops: the faces stay still pictures

    act(() => {
      liveCallPresentationStore.resetForTests();
      callSceneStore.resetForTests();
      resetMemberLoops();
    });
  });

  it("idles a failing portrait on its loop only when its fallback is a still picture; a moving fallback is kept", () => {
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => 'blob:loop');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const still = { ...mayaRuntime.avatar_pack, character_id: 'leo', renderer: 'portrait', fallback_renderer: 'sprite',
      base_asset_id: 'image:leo-portrait' } as CharacterLiveCallRuntime['avatar_pack'];
    const talking = { ...still, mouth_frames: { closed: 'image:leo-closed', wide: 'image:leo-wide' } } as typeof still;
    rememberMemberLoop('chat:maya', 'leo', { frameMs: 80, idle: [new Uint8Array([1])], blink: [] }, packRevision(still));
    const { result, rerender } = renderHook(({ pack }) => useDrawnAvatarPack(pack, 'leo'), { initialProps: { pack: still } });
    act(() => {
      const hooks = livePortrait.begin('chat:maya', { id: 'leo', pack: still });
      hooks.onHello({ callKey: 'call', avatarToken: 'token' });
    });
    const socket = sockets.at(-1) as { emit: (type: string, event: unknown) => void };
    act(() => socket.emit('message', { data: JSON.stringify({ type: 'unavailable', code: 'portrait_busy' }) }));
    expect(result.current.pack?.renderer).toBe('portrait'); // its loop, not the uncropped still
    expect(result.current.mine).toBe(false); // the failed stream is not drawn
    expect(result.current.notice).toBe(portraitNotice(livePortrait.getSnapshot())); // and why is still said

    rerender({ pack: talking });
    expect(result.current.pack?.renderer).toBe('sprite'); // a mouth that moves beats a silent loop

    act(() => {
      livePortrait.end();
      resetMemberLoops();
    });
  });

  it('seats a full call of five: the host and four guests each get a tile', async () => {
    const guests = ['leo', 'ivy', 'ana', 'kai'];
    const members = [
      { character_id: 'maya', display_name: 'Maya', role: 'host', seat: 0 },
      ...guests.map((id, index) => ({ character_id: id, display_name: id[0].toUpperCase() + id.slice(1), role: 'guest', seat: index + 1 })),
    ];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const body = new URL(raw, window.location.origin).pathname.endsWith('/scene')
        ? { available: true, reason: 'ready', max_guests: 4, members }
        : { detail: 'not_found' };
      return new Response(JSON.stringify(body), { status: 'members' in body ? 200 : 404, headers: { 'Content-Type': 'application/json' } });
    });
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:maya' });
    enterLiveChatFullscreen('header');
    renderShell();
    act(() => publishCharacterAvatarRuntime(mayaRuntime));
    await act(async () => { await loadCallScene('chat:maya'); });

    const room = await screen.findByRole('list', { name: 'Call members' });
    expect(room.dataset.members).toBe('5');
    expect(within(room).getAllByRole('listitem').map((tile) => tile.dataset.role)).toEqual(['host', 'guest', 'guest', 'guest', 'guest']);
    expect(within(room).getByLabelText('Kai visual placeholder')).toBeTruthy();

    act(() => callSceneStore.resetForTests());
  });

  it('hands call and composer actions to Chat', () => {
    enterLiveChatFullscreen('call-card');
    renderShell();

    fireEvent.click(screen.getByRole('button', { name: 'End voice chat' }));
    expect(sourceCallClick).toHaveBeenCalledTimes(1);

    const composer = screen.getByPlaceholderText('Write a message…');
    fireEvent.change(composer, { target: { value: 'A fullscreen message' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send fullscreen Live Chat message' }));
    expect(sourceSubmit).toHaveBeenCalledWith('A fullscreen message');
    expect(composer).toHaveValue('');
  });

  it('exits the overlay without ending the call', async () => {
    enterLiveChatFullscreen('header');
    renderShell();

    fireEvent.click(screen.getByRole('button', { name: 'Exit fullscreen Live Chat' }));
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sourceCallClick).not.toHaveBeenCalled();
  });
});
