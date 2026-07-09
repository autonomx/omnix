import { afterEach, describe, expect, it, vi } from 'vitest';
import { characterClient } from './characterClient';

afterEach(() => vi.unstubAllGlobals());

describe('characterClient live-call runtime', () => {
  it('loads the trusted runtime for the selected chat session', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input.toString()).toBe('/api/chat/sessions/chat%3Aone/live-call/runtime');
      return Response.json({
        session_id: 'chat:one',
        interaction_mode: 'character',
        display_name: 'Maya',
        character_id: 'maya',
        character_profile_version: 3,
        effective_identity_hash: 'a'.repeat(64),
        voice_asset_id: 'voice-cloning:maya',
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
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const runtime = await characterClient.liveCallRuntime('chat:one');

    expect(runtime.character_id).toBe('maya');
    expect(runtime.voice_asset_id).toBe('voice-cloning:maya');
    expect(runtime.speech_style.speed).toBe(0.94);
    expect(runtime.preload.memory_record_count).toBe(4);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
