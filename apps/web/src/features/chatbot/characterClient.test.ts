import { afterEach, describe, expect, it, vi } from 'vitest';
import { characterClient, type CharacterLiveCallRuntime } from './characterClient';

afterEach(() => vi.unstubAllGlobals());

function runtime(overrides: Partial<CharacterLiveCallRuntime> = {}): CharacterLiveCallRuntime {
  return {
    session_id: 'chat:one',
    interaction_mode: 'character',
    display_name: 'Maya',
    character_id: 'maya',
    character_profile_version: 3,
    effective_identity_hash: 'a'.repeat(64),
    voice_asset_id: 'voice-cloning:maya',
    voice_speaker_id: 'Maya',
    greeting: 'Hey, good to hear from you.',
    speech_style: {
      speed: 0.94,
      temperature: 0.52,
      top_k: 18,
      top_p: 0.82,
      repetition_penalty: 1.05,
      expressiveness: 'relaxed',
      emotion: 'calm',
      interruption_style: 'patient',
    },
    read_memory: true,
    write_memory: false,
    shared_memory_access: 'none',
    memory_snapshot_id: 'memory-snapshot:one',
    preload: {
      profile_loaded: true,
      voice_resolved: true,
      memory_snapshot_loaded: true,
      memory_record_count: 4,
      preload_ms: 1.25,
      resolved_at: '2026-07-09T00:00:00Z',
    },
    ...overrides,
  };
}

describe('characterClient live-call runtime', () => {
  it('loads the trusted runtime for the selected chat session', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input.toString()).toBe('/api/chat/sessions/chat%3Aone/live-call/runtime');
      return Response.json(runtime());
    });
    vi.stubGlobal('fetch', fetchMock);

    const resolved = await characterClient.liveCallRuntime('chat:one');

    expect(resolved.character_id).toBe('maya');
    expect(resolved.voice_asset_id).toBe('Maya');
    expect(resolved.voice_profile_asset_id).toBe('voice-cloning:maya');
    expect(resolved.speech_style.speed).toBe(0.94);
    expect(resolved.preload.memory_record_count).toBe(4);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('updates an already-referenced playback runtime when the linked voice changes', async () => {
    let requestCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input.toString()).toBe('/api/chat/sessions/chat%3Ahot-swap/live-call/runtime');
      requestCount += 1;
      return Response.json(requestCount === 1
        ? runtime({ session_id: 'chat:hot-swap' })
        : runtime({
            session_id: 'chat:hot-swap',
            character_profile_version: 4,
            voice_asset_id: 'voice-cloning:inigo',
            voice_speaker_id: 'Inigo',
          }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const activeRuntimeReference = await characterClient.liveCallRuntime('chat:hot-swap');
    const refreshedRuntime = await characterClient.refreshLiveCallRuntime('chat:hot-swap');

    expect(refreshedRuntime.voice_asset_id).toBe('Inigo');
    expect(refreshedRuntime.voice_profile_asset_id).toBe('voice-cloning:inigo');
    expect(activeRuntimeReference.voice_asset_id).toBe('Inigo');
    expect(activeRuntimeReference.voice_speaker_id).toBe('Inigo');
    expect(activeRuntimeReference.voice_profile_asset_id).toBe('voice-cloning:inigo');
    expect(activeRuntimeReference.character_profile_version).toBe(4);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
