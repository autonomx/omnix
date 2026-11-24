import { QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../../../test/renderWithProviders';
import { characterAvatarClient } from '../characterAvatarClient';
import type { CharacterAvatarPack } from '../characterClient';
import { CastPortraitLoadControl } from './CastPortraitLoadControl';
import type { StageCharacter } from './CharacterStage';
import { memberLoop, packRevision, resetMemberLoops } from './memberIdleLoops';

const IDLE_PATH = '/api/tts/live-call/portrait-idle';
const LOOP = { ok: true, frame_ms: 80, idle: [btoa('a')], blink: [] };
let idleAsks: URL[] = [];

const pack = (id: string, renderer = 'portrait') => ({ character_id: id, version: 1, renderer, base_asset_id: `image:${id}` }) as CharacterAvatarPack;
const CAST: StageCharacter[] = [
  { id: 'char:maya', name: 'Maya', pack: pack('char:maya') },
  { id: 'char:bea', name: 'Bea', pack: pack('char:bea') },
  { id: 'char:ian', name: 'Ian', pack: pack('char:ian', 'sprite') },
];

function show(disabled = false) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <CastPortraitLoadControl runKey="podcast-stage:t" members={CAST} disabled={disabled} />
    </QueryClientProvider>,
  );
}

describe('"Load live avatars" for a podcast cast', () => {
  beforeEach(() => {
    window.localStorage.clear();
    idleAsks = [];
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => 'blob:frame');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const url = new URL(raw, window.location.origin);
      if (url.pathname === IDLE_PATH) idleAsks.push(url);
      return Response.json(url.pathname === IDLE_PATH ? LOOP : {});
    }));
  });

  afterEach(() => {
    cleanup();
    act(() => resetMemberLoops());
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('loads the model and every portrait face before the podcast, then unloads on a second press', async () => {
    let state: 'unloaded' | 'ready' = 'unloaded';
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockImplementation(async () => ({ status: state }));
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait')
      .mockResolvedValueOnce({ status: 'loading', code: 'warming', message: 'loading' })
      .mockImplementation(async () => {
        state = 'ready';
        return { status: 'ready', code: '', message: '' };
      });
    const unload = vi.spyOn(characterAvatarClient, 'unloadPortrait').mockResolvedValue({ ok: true, code: '', message: '' });
    show();

    fireEvent.click(await screen.findByRole('button', { name: 'Load live avatars' }));
    expect(await screen.findByRole('button', { name: 'Live avatars ready' }, { timeout: 4000 })).toHaveAttribute('aria-pressed', 'true');

    // Each portrait face is prepared (Ian's sprite is not); the first was asked again once the model was up.
    expect(load.mock.calls.map(([assetId]) => assetId)).toEqual(['image:char:maya', 'image:char:maya', 'image:char:bea']);
    // Their loops come by character, not by chat.
    expect(idleAsks.map((url) => url.searchParams.get('character_id'))).toEqual(['char:maya', 'char:bea']);
    expect(idleAsks.every((url) => !url.searchParams.has('session_id'))).toBe(true);
    expect(memberLoop('char:bea', packRevision(CAST[1].pack))).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Live avatars ready' }));
    await waitFor(() => expect(unload).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('button', { name: 'Load live avatars' })).toBeInTheDocument();
    expect(memberLoop('char:bea', packRevision(CAST[1].pack))).toBeNull();
  });

  it('is ready, and can unload, when a face is prepared but its loop is not handed back yet', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    vi.spyOn(characterAvatarClient, 'loadPortrait').mockResolvedValue({ status: 'ready', code: '', message: '' });
    vi.spyOn(characterAvatarClient, 'unloadPortrait').mockResolvedValue({ ok: true, code: '', message: '' });
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ ok: false, code: 'not_rendered', message: '' })));
    show();

    fireEvent.click(await screen.findByRole('button', { name: 'Load live avatars' }));
    expect(await screen.findByRole('button', { name: 'Live avatars ready' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('Some idle loops are not ready yet');
  });

  it('says why when the service refuses, and is not pressable while the podcast generates', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'unloaded' });
    vi.spyOn(characterAvatarClient, 'loadPortrait').mockResolvedValue({ status: 'unavailable', code: 'model_busy', message: '' });
    const view = show();

    fireEvent.click(await screen.findByRole('button', { name: 'Load live avatars' }));
    expect(await screen.findByRole('status')).toHaveTextContent(/Live portrait/);

    view.unmount();
    show(true);
    expect(await screen.findByRole('button', { name: 'Load live avatars' })).toBeDisabled();
  });
});
