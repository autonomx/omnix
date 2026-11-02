import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../../test/renderWithProviders';
import { characterClient, type CharacterAvatarPack, type CharacterLiveCallRuntime } from './characterClient';
import { characterAvatarClient } from './characterAvatarClient';
import { liveAvatarStore, publishCharacterAvatarRuntime } from './liveCharacterAvatarBridge';
import { neutralSystemLiveCallRuntime, NEUTRAL_SPEECH_STYLE } from './neutralLiveCallRuntime';
import { useLiveCallRuntime } from './useLiveCallRuntime';

const pack = {
  character_id: 'maya', renderer: 'portrait', base_asset_id: 'image:maya', fallback_renderer: 'sprite', mouth_frames: {},
  blink_frames: {}, expression_frames: {}, outfit_frames: {}, background_asset_ids: {}, mouth_anchor: {},
} as unknown as CharacterAvatarPack;
const realRuntime: CharacterLiveCallRuntime = {
  ...neutralSystemLiveCallRuntime('chat:one', null, NEUTRAL_SPEECH_STYLE),
  interaction_mode: 'character',
  character_id: 'maya',
  display_name: 'Maya',
  avatar_pack: { ...pack, base_asset_id: 'image:real' },
};
type Options = Parameters<typeof useLiveCallRuntime>[0];
const character = { interaction_mode: 'character', character_id: 'maya' } as NonNullable<Options['interaction']>;

function renderRuntime(overrides: Partial<Options> = {}) {
  const client = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return renderHook(() => useLiveCallRuntime({
    selectedSessionId: 'chat:one',
    selectedSessionSummary: { interaction_mode: 'character', character_id: 'maya' } as Options['selectedSessionSummary'],
    interaction: character,
    characterName: 'Maya',
    liveVoiceActiveRef: { current: false },
    ...overrides,
  }), { wrapper });
}

afterEach(() => {
  vi.restoreAllMocks();
  publishCharacterAvatarRuntime(null);
});

describe('the avatar before the live-call runtime', () => {
  it('draws the chat character\'s avatar at once, without making it the call\'s runtime', async () => {
    const optionalPack = vi.spyOn(characterAvatarClient, 'optionalPack').mockResolvedValue(pack);
    vi.spyOn(characterClient, 'liveCallRuntime').mockReturnValue(new Promise(() => undefined)); // its memory is loading

    const { result } = renderRuntime();

    await waitFor(() => expect(liveAvatarStore.getState().runtime?.avatar_pack).toBe(pack));
    expect(optionalPack).toHaveBeenCalledWith('maya');
    expect(liveAvatarStore.getState().runtime).toMatchObject({ display_name: 'Maya', interaction_mode: 'character', session_id: '' });
    expect(result.current.liveCallRuntime).toBeNull();
    expect(result.current.liveCallRuntimeRef.current).toBeNull();
    expect(result.current.liveCallRuntimeLoading).toBe(true);
  });

  it('leaves the real runtime in place when the avatar arrives after it', async () => {
    let finishPack: (value: CharacterAvatarPack) => void = () => undefined;
    vi.spyOn(characterAvatarClient, 'optionalPack').mockReturnValue(new Promise((resolve) => { finishPack = resolve; }));
    vi.spyOn(characterClient, 'liveCallRuntime').mockImplementation(async () => {
      publishCharacterAvatarRuntime(realRuntime); // as the client does when a runtime loads
      return realRuntime;
    });

    const { result } = renderRuntime();
    await waitFor(() => expect(result.current.liveCallRuntime).toBe(realRuntime));
    finishPack(pack);
    await new Promise((resolve) => { setTimeout(resolve, 20); });

    expect(liveAvatarStore.getState().runtime).toBe(realRuntime);
    expect(result.current.liveCallRuntimeLoading).toBe(false);
  });

  it('does not touch the picture while a call is running', async () => {
    vi.spyOn(characterAvatarClient, 'optionalPack').mockResolvedValue(pack);
    vi.spyOn(characterClient, 'liveCallRuntime').mockReturnValue(new Promise(() => undefined));

    renderRuntime({ liveVoiceActiveRef: { current: true } });
    await new Promise((resolve) => { setTimeout(resolve, 20); });

    expect(liveAvatarStore.getState().runtime).toBeNull();
  });

  it('asks for the System Assistant\'s avatar in a system chat, and for nothing while the chat is unknown', async () => {
    const optionalPack = vi.spyOn(characterAvatarClient, 'optionalPack').mockResolvedValue(null);
    vi.spyOn(characterClient, 'liveCallRuntime').mockReturnValue(new Promise(() => undefined));

    renderRuntime({ interaction: undefined, selectedSessionSummary: undefined });
    await new Promise((resolve) => { setTimeout(resolve, 20); });
    expect(optionalPack).not.toHaveBeenCalled();

    renderRuntime({
      interaction: { interaction_mode: 'system', character_id: null } as NonNullable<Options['interaction']>,
      selectedSessionSummary: undefined,
    });
    await waitFor(() => expect(optionalPack).toHaveBeenCalledWith('system-assistant'));
  });
});
