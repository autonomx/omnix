import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const audioMocks = vi.hoisted(() => ({
  playBufferedTts: vi.fn().mockResolvedValue(undefined),
  stopBufferedTtsPlayback: vi.fn(),
  stopAssistantPcmStream: vi.fn(),
}));

vi.mock('./assistant-buffered-tts-player', () => ({
  playBufferedTts: audioMocks.playBufferedTts,
  stopBufferedTtsPlayback: audioMocks.stopBufferedTtsPlayback,
}));
vi.mock('./assistant-pcm-stream-websocket-player', () => ({
  stopAssistantPcmStream: audioMocks.stopAssistantPcmStream,
}));

import { characterClient, type CharacterLiveCallRuntime } from '../chatbot/characterClient';
import { liveConversationStore } from './live-conversation-store';
import {
  initializeChatMessageAudioControllerV2,
  resolveChatMessageAudioVoiceId,
} from './chat-message-audio-controller-v2';

let cleanupController: (() => void) | null = null;

function trustedRuntime(
  overrides: Partial<CharacterLiveCallRuntime> = {},
): CharacterLiveCallRuntime {
  return {
    session_id: 'chat:jinx',
    interaction_mode: 'character',
    display_name: 'Jinx',
    character_id: 'jinx',
    character_profile_version: 4,
    effective_identity_hash: 'a'.repeat(64),
    voice_asset_id: 'voice-cloning:jinx',
    voice_speaker_id: 'Jinx',
    greeting: '',
    speech_style: {
      speed: 1,
      temperature: 0.6,
      top_k: 20,
      top_p: 0.85,
      repetition_penalty: 1,
      expressiveness: 'neutral',
      emotion: 'neutral',
      interruption_style: 'balanced',
    },
    read_memory: true,
    write_memory: false,
    shared_memory_access: 'read_only',
    preload: {
      profile_loaded: true,
      voice_resolved: true,
      memory_snapshot_loaded: false,
      memory_record_count: 0,
      preload_ms: 1,
      resolved_at: '2026-08-01T00:00:00Z',
    },
    ...overrides,
  };
}

async function retainRuntime(runtime = trustedRuntime()): Promise<void> {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json(runtime)));
  await characterClient.liveCallRuntime(runtime.session_id);
}

function renderBufferedAudioMessage(
  identity = 'Jinx is active in Live Voice',
  renderedVoice = '',
): HTMLButtonElement {
  document.body.innerHTML = `
    <section class="assistant-live-card" data-live-voice-id="${renderedVoice}">
      <span class="assistant-live-identity">${identity}</span>
    </section>
    <article class="assistant-chat-message assistant">
      <div class="assistant-chat-bubble">
        <p>Play this reply.</p>
        <div class="assistant-message-actions">
          <button type="button" aria-label="Play response audio">Play audio</button>
        </div>
      </div>
    </article>
    <div class="assistant-inline-status"></div>`;
  cleanupController = initializeChatMessageAudioControllerV2();
  return document.querySelector<HTMLButtonElement>('button[aria-label="Play response audio"]') as HTMLButtonElement;
}

afterEach(() => {
  cleanupController?.();
  cleanupController = null;
  document.body.innerHTML = '';
  liveConversationStore.reset();
  window.localStorage.clear();
  audioMocks.playBufferedTts.mockClear();
  audioMocks.stopBufferedTtsPlayback.mockClear();
  audioMocks.stopAssistantPcmStream.mockClear();
  vi.unstubAllGlobals();
});

describe('buffered chat response voice resolution', () => {
  it('uses and logs the retained trusted speaker when the rendered voice attribute is empty', async () => {
    await retainRuntime();
    const button = renderBufferedAudioMessage();
    const diagnostics = vi.fn();
    window.addEventListener('omnix:live-call-diagnostic', diagnostics);

    fireEvent.click(button);

    await waitFor(() => expect(audioMocks.playBufferedTts).toHaveBeenCalledTimes(1));
    expect(audioMocks.playBufferedTts).toHaveBeenCalledWith(
      'Play this reply.',
      expect.objectContaining({ voiceId: 'Jinx' }),
    );
    expect(resolveChatMessageAudioVoiceId()).toBe('Jinx');

    const decision = diagnostics.mock.calls
      .map((call) => call[0] as CustomEvent)
      .find((event) => event.detail.event === 'voice_resolution_decision');
    expect(decision?.detail).toEqual(expect.objectContaining({
      source: 'voice-resolution',
      event: 'voice_resolution_decision',
      details: expect.objectContaining({
        caller: 'manual-play',
        final_voice_id: 'Jinx',
        final_source: 'trusted_runtime_speaker',
        playback_voice_id: 'Jinx',
        spoken_text_length: 16,
        character_decision: expect.objectContaining({
          runtime_session_id: 'chat:jinx',
          runtime_character_id: 'jinx',
          runtime_voice_speaker_id: 'Jinx',
          runtime_voice_resolved: true,
          same_displayed_character: true,
        }),
      }),
    }));
    window.removeEventListener('omnix:live-call-diagnostic', diagnostics);
  });

  it('prefers the fresh trusted runtime over a stale rendered voice after reassignment', async () => {
    await retainRuntime();
    const button = renderBufferedAudioMessage('Jinx is active in Live Voice', 'Inigo');

    fireEvent.click(button);

    await waitFor(() => expect(audioMocks.playBufferedTts).toHaveBeenCalledTimes(1));
    expect(audioMocks.playBufferedTts).toHaveBeenCalledWith(
      'Play this reply.',
      expect.objectContaining({ voiceId: 'Jinx' }),
    );
    expect(resolveChatMessageAudioVoiceId()).toBe('Jinx');
  });

  it('rejects a retained Jinx runtime when another character is displayed', async () => {
    await retainRuntime();
    renderBufferedAudioMessage('Maya is active in Live Voice');

    expect(resolveChatMessageAudioVoiceId()).toBeNull();
  });
});
