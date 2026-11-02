import { QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../../../test/renderWithProviders';
import { fixture } from '../../../../test/fixture';
import { characterAvatarClient } from '../characterAvatarClient';
import type { CharacterLiveCallRuntime } from '../characterClient';
import { publishCharacterAvatarRuntime } from '../liveCharacterAvatarBridge';
import { livePortrait } from './livePortrait';
import { LivePortraitLoadControl } from './LivePortraitLoadControl';

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
    act(() => publishCharacterAvatarRuntime(runtime('portrait')));
  });

  afterEach(() => {
    cleanup();
    act(() => {
      publishCharacterAvatarRuntime(null);
      livePortrait.end();
    });
    vi.restoreAllMocks();
  });

  it('loads the portrait\'s model on request, asking until it is ready', async () => {
    let state: 'unloaded' | 'ready' = 'unloaded';
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockImplementation(async () => ({ status: state }));
    const load = vi.spyOn(characterAvatarClient, 'loadPortrait')
      .mockResolvedValueOnce({ status: 'loading', code: 'warming', message: 'loading' })
      .mockImplementationOnce(async () => {
        state = 'ready';
        return { status: 'ready', code: '', message: '' };
      });
    show();

    const button = await screen.findByRole('button', { name: 'Load live video' });
    expect(load).not.toHaveBeenCalled(); // nothing loads until it is pressed
    fireEvent.click(button);
    expect(await screen.findByRole('button', { name: 'Loading live video…' })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Live video ready' })).toBeDisabled(), { timeout: 4_000 });
    expect(load).toHaveBeenCalledTimes(2);
    expect(load).toHaveBeenCalledWith('image:maya');
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

  it('shows a model already loaded as ready', async () => {
    vi.spyOn(characterAvatarClient, 'portraitModelStatus').mockResolvedValue({ status: 'ready' });
    show();
    expect(await screen.findByRole('button', { name: 'Live video ready' })).toBeDisabled();
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
