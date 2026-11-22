import { QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../../../test/renderWithProviders';
import { fixture } from '../../../../test/fixture';
import { characterAvatarClient } from '../characterAvatarClient';
import type { CharacterLiveCallRuntime } from '../characterClient';
import { publishCharacterAvatarRuntime } from '../liveCharacterAvatarBridge';
import { liveConversationStore } from '../../workspace/live-conversation-store';
import { callSceneStore, loadCallScene } from '../../workspace/live-call-scene';
import { livePortrait, liveVideoRequested, requestLiveVideo, resetLiveVideoRequests } from './livePortrait';
import { LivePortraitLoadControl } from './LivePortraitLoadControl';
import { memberLoop, packRevision, resetMemberLoops } from './memberIdleLoops';

const IDLE_PATH = '/api/tts/live-call/portrait-idle';
const LOOP = { ok: true, frame_ms: 80, idle: [btoa('a'), btoa('b')], blink: [] };
let idleReplies: Record<string, unknown>[] = [];
let idleAsks: URL[] = [];
let sceneReply: Record<string, unknown> = {};

function runtime(renderer: string): CharacterLiveCallRuntime {
  return fixture({
    session_id: 'chat:maya', interaction_mode: 'character', display_name: 'Maya', character_id: 'maya',
    avatar_pack: {
      character_id: 'maya', version: 1, render_mode: 'static', renderer, rig_asset_id: null, base_asset_id: 'image:maya',
      fallback_renderer: 'sprite', mouth_frames: {}, blink_frames: {}, expression_frames: {}, outfit_frames: {}, background_asset_ids: {},
    },
  });
}

function show() {
  return render(<QueryClientProvider client={createTestQueryClient()}><LivePortraitLoadControl /></QueryClientProvider>);
}

describe('the load live video button', () => {
  beforeEach(() => {
    window.localStorage.clear();
    idleReplies = [];
    idleAsks = [];
    sceneReply = {};
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => 'blob:frame');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const url = new URL(raw, window.location.origin);
      if (url.pathname === IDLE_PATH) idleAsks.push(url);
      const body = url.pathname === IDLE_PATH ? idleReplies.shift() ?? { ok: false, code: 'portrait_failed' }
        : url.pathname.endsWith('/scene') ? sceneReply : {};
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    liveConversationStore.reset();
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:maya' });
    act(() => publishCharacterAvatarRuntime(runtime('portrait')));
  });

  afterEach(() => {
    cleanup();
    act(() => {
      publishCharacterAvatarRuntime(null);
      livePortrait.end();
      resetMemberLoops();
      resetLiveVideoRequests();
      callSceneStore.resetForTests();
    });
    liveConversationStore.reset();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const loopKnown = () => memberLoop('maya', packRevision(runtime('portrait').avatar_pack)) !== null;

  it('loads the portrait\'s model on request, asking until it is ready, then plays its idle loop', async () => {
    let state: 'unloaded' | 'ready' = 'unloaded';
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockImplementation(async () => ({ status: state }));
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait')
      .mockResolvedValueOnce({ status: 'loading', code: 'warming', message: 'loading' })
      .mockImplementationOnce(async () => {
        state = 'ready';
        return { status: 'ready', code: '', message: '' };
      });
    idleReplies.push(LOOP);
    show();

    const button = await screen.findByRole('button', { name: 'Load live video' });
    expect(load).not.toHaveBeenCalled(); // nothing loads until it is pressed
    expect(idleAsks).toEqual([]);
    expect(liveVideoRequested('chat:maya')).toBe(false);
    fireEvent.click(button);
    expect(liveVideoRequested('chat:maya')).toBe(true); // the chat's calls now bring the video up
    expect(await screen.findByRole('button', { name: 'Loading live video…' })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true'), { timeout: 4_000 });
    expect(load).toHaveBeenCalledTimes(2);
    expect(load).toHaveBeenCalledWith('image:maya');
    // The stage plays the chat's own character's loop before the call.
    expect(loopKnown()).toBe(true);
    expect(idleAsks[0].searchParams.get('session_id')).toBe('chat:maya');
    expect(idleAsks[0].searchParams.has('speaker_id')).toBe(false);
  });

  it('says why the service refused, and can be pressed again', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'unloaded' });
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait')
      .mockResolvedValue({ status: 'unavailable', code: 'model_busy', message: 'short' });
    show();

    fireEvent.click(await screen.findByRole('button', { name: 'Load live video' }));
    expect((await screen.findByRole('status')).textContent).toContain('not enough memory');
    fireEvent.click(screen.getByRole('button', { name: 'Load live video' }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it('shows a model already loaded as ready once its loop is known, in a chat that asked for video', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait');
    requestLiveVideo('chat:maya');
    idleReplies.push(LOOP);
    show();
    expect(await screen.findByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(loopKnown()).toBe(true);
    expect(load).not.toHaveBeenCalled();
  });

  it('pressed again once ready, unloads the model and turns video off for the chat', async () => {
    let state: 'unloaded' | 'ready' = 'ready';
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockImplementation(async () => ({ status: state }));
    const unload = vi.spyOn(characterAvatarClient, 'unloadPortrait').mockImplementation(async () => {
      state = 'unloaded';
      return { ok: true, code: '', message: '' };
    });
    requestLiveVideo('chat:maya');
    idleReplies.push(LOOP);
    show();

    const ready = await screen.findByRole('button', { name: 'Live video ready' });
    expect(ready).toBeEnabled();
    expect(ready).toHaveAttribute('title', 'Unload live video');
    fireEvent.click(ready);
    expect(await screen.findByRole('button', { name: 'Load live video' })).toHaveAttribute('aria-pressed', 'false');
    expect(unload).toHaveBeenCalledTimes(1);
    expect(liveVideoRequested('chat:maya')).toBe(false); // the next call is voice only
    expect(loopKnown()).toBe(false); // the faces are still pictures again
  });

  it('keeps the video when the service refuses the unload, and says why', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    vi.spyOn(characterAvatarClient, 'unloadPortrait')
      .mockResolvedValue({ ok: false, code: 'model_busy', message: 'A call is using the portrait' });
    requestLiveVideo('chat:maya');
    idleReplies.push(LOOP);
    show();

    fireEvent.click(await screen.findByRole('button', { name: 'Live video ready' }));
    expect((await screen.findByRole('status')).textContent).toBe('A call is using the portrait');
    expect(screen.getByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(liveVideoRequested('chat:maya')).toBe(true);
    expect(loopKnown()).toBe(true);
  });

  it('a model already loaded still waits for a press in a chat that has not asked for video', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait').mockResolvedValue({ status: 'ready', code: '', message: '' });
    idleReplies.push(LOOP);
    show();

    const button = await screen.findByRole('button', { name: 'Load live video' });
    expect(button).toBeEnabled();
    await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 20); }); });
    expect(idleAsks).toEqual([]); // no loop, so the stage stays a still picture
    fireEvent.click(button);
    expect(await screen.findByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(load).toHaveBeenCalledOnce();
    expect(loopKnown()).toBe(true);
  });

  it('a model loaded for another face can still be pressed, and pressing renders this face\'s loop', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    vi.spyOn(characterAvatarClient, 'loadPortrait').mockResolvedValue({ status: 'ready', code: '', message: '' });
    requestLiveVideo('chat:maya');
    idleReplies.push({ ok: false, code: 'portrait_failed' });
    show();

    await waitFor(() => expect(idleAsks).toHaveLength(1));
    const button = await screen.findByRole('button', { name: 'Load live video' });
    expect(button).toBeEnabled();
    idleReplies.push(LOOP);
    fireEvent.click(button);
    expect(await screen.findByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(idleAsks).toHaveLength(2);
    expect(loopKnown()).toBe(true);
  });

  it("renders an invited guest's loop too, so the guest idles live before the call", async () => {
    const guestPack = { ...runtime('portrait').avatar_pack, character_id: 'abhishek', base_asset_id: 'image:abhishek' };
    act(() => publishCharacterAvatarRuntime(fixture<CharacterLiveCallRuntime>({
      ...runtime('portrait'),
      scene_guests: [{ character_id: 'abhishek', display_name: 'Abhishek', voice_asset_id: null, voice_speaker_id: null,
        speech_style: null, avatar_pack: guestPack }],
    })));
    sceneReply = { available: true, reason: 'ready', max_guests: 2, members: [
      { character_id: 'maya', display_name: 'Maya', role: 'host', seat: 0 },
      { character_id: 'abhishek', display_name: 'Abhishek', role: 'guest', seat: 1 },
    ] };
    await act(async () => { await loadCallScene('chat:maya'); });
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait').mockResolvedValue({ status: 'ready', code: '', message: '' });
    idleReplies.push(LOOP, LOOP, LOOP);
    show();

    const button = await screen.findByRole('button', { name: 'Load live video' });
    expect(load).not.toHaveBeenCalled(); // nothing is rendered before the press
    fireEvent.click(button);
    expect(await screen.findByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(load).toHaveBeenCalledWith('image:maya');
    expect(load).toHaveBeenCalledWith('image:abhishek');
    expect(memberLoop('abhishek', packRevision(guestPack))).not.toBeNull();
    expect(idleAsks.some((ask) => ask.searchParams.get('speaker_id') === 'abhishek')).toBe(true);
  });

  it('shows the load\'s progress step by step: the model, the face, then each guest', async () => {
    const guestPack = { ...runtime('portrait').avatar_pack, character_id: 'abhishek', base_asset_id: 'image:abhishek' };
    act(() => publishCharacterAvatarRuntime(fixture<CharacterLiveCallRuntime>({
      ...runtime('portrait'),
      scene_guests: [{ character_id: 'abhishek', display_name: 'Abhishek', voice_asset_id: null, voice_speaker_id: null,
        speech_style: null, avatar_pack: guestPack }],
    })));
    sceneReply = { available: true, reason: 'ready', max_guests: 2, members: [
      { character_id: 'maya', display_name: 'Maya', role: 'host', seat: 0 },
      { character_id: 'abhishek', display_name: 'Abhishek', role: 'guest', seat: 1 },
    ] };
    await act(async () => { await loadCallScene('chat:maya'); });
    let state: 'unloaded' | 'loading' | 'ready' = 'unloaded';
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockImplementation(async () => ({ status: state }));
    const answers: Record<string, () => void> = {};
    vi.spyOn(characterAvatarClient, 'loadPortrait').mockImplementation((asset: string) => {
      if (state !== 'ready') {
        state = 'ready'; // the model comes up while the button waits
        return Promise.resolve({ status: 'loading' as const, code: 'warming', message: 'loading' });
      }
      return new Promise((resolve) => { answers[asset] = () => resolve({ status: 'ready', code: '', message: '' }); });
    });
    idleReplies.push(LOOP, LOOP);
    show();

    fireEvent.click(await screen.findByRole('button', { name: 'Load live video' }));
    const bar = await screen.findByRole('progressbar', { name: 'Loading live video' });
    expect(bar.getAttribute('aria-valuetext')).toMatch(/^Loading the portrait model… \d+%$/);
    expect(screen.getByText(/^Step 1 of 3 · about \d+ s left$/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Rendering Maya's live video…")).toBeInTheDocument(), { timeout: 4_000 });
    expect(screen.getByText(/^Step 2 of 3/)).toBeInTheDocument();
    await act(async () => { answers['image:maya'](); });
    await waitFor(() => expect(screen.getByText('Preparing Abhishek…')).toBeInTheDocument());
    expect(screen.getByText(/^Step 3 of 3/)).toBeInTheDocument();
    expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeGreaterThan(0);
    await act(async () => { answers['image:abhishek'](); });
    expect(await screen.findByRole('button', { name: 'Live video ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('slides without steps while a load it did not start is under way', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'loading' });
    show();
    const bar = await screen.findByRole('progressbar', { name: 'Loading live video' });
    expect(bar).not.toHaveAttribute('aria-valuenow');
    expect(screen.getByRole('button', { name: 'Loading live video…' })).toBeDisabled();
  });

  it('is there only for a portrait, outside a call, with the portrait service set up', async () => {
    const status = vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'unloaded' });
    const view = show();
    await screen.findByRole('button', { name: 'Load live video' });

    act(() => publishCharacterAvatarRuntime(runtime('sprite')));
    expect(screen.queryByRole('button')).toBeNull();

    act(() => publishCharacterAvatarRuntime(runtime('portrait')));
    expect(await screen.findByRole('button', { name: 'Load live video' })).toBeTruthy();
    act(() => { livePortrait.begin('chat:maya'); });
    expect(screen.queryByRole('button')).toBeNull();
    act(() => livePortrait.end());
    expect(await screen.findByRole('button', { name: 'Load live video' })).toBeTruthy();
    view.unmount();

    status.mockResolvedValue({ status: 'unavailable' });
    show();
    await waitFor(() => expect(status).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole('button')).toBeNull());
  });
});
