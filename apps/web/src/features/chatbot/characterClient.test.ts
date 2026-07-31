import { afterEach, describe, expect, it, vi } from 'vitest';
import { characterClient } from './characterClient';

afterEach(() => vi.unstubAllGlobals());

describe('characterClient live-call runtime', () => {
  it('keeps the governed asset for diagnostics and uses the resolved speaker for playback', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input.toString()).toBe('/api/chat/sessions/chat%3Aone/live-call/runtime');
      return Response.json({
        session_id: 'chat:one',
        interaction_mode: 'character',
        display_name: 'Jinx',
        character_id: 'jinx',
        character_profile_version: 3,
        effective_identity_hash: 'a'.repeat(64),
        voice_asset_id: 'voice-cloning:jinx',
        voice_speaker_id: 'Jinx',
        greeting: '',
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
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const runtime = await characterClient.liveCallRuntime('chat:one');

    expect(runtime.character_id).toBe('jinx');
    expect(runtime.voice_profile_asset_id).toBe('voice-cloning:jinx');
    expect(runtime.voice_asset_id).toBe('Jinx');
    expect(runtime.voice_speaker_id).toBe('Jinx');
    expect(runtime.speech_style.speed).toBe(0.94);
    expect(runtime.preload.memory_record_count).toBe(4);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('preserves the legacy asset field when no resolved speaker is supplied', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      session_id: 'chat:legacy',
      interaction_mode: 'system',
      display_name: 'System Assistant',
      voice_asset_id: 'voice-cloning:legacy',
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
      read_memory: false,
      write_memory: false,
      shared_memory_access: 'none',
      preload: {
        profile_loaded: false,
        voice_resolved: true,
        memory_snapshot_loaded: false,
        memory_record_count: 0,
        preload_ms: 0,
        resolved_at: '2026-07-09T00:00:00Z',
      },
    })));

    const runtime = await characterClient.liveCallRuntime('chat:legacy');

    expect(runtime.voice_asset_id).toBe('voice-cloning:legacy');
    expect(runtime.voice_profile_asset_id).toBeUndefined();
  });
});
