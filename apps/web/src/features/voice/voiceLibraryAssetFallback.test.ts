import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  installVoiceLibraryAssetFallback,
  resetVoiceLibraryAssetFallbackForTests,
} from './voiceLibraryAssetFallback';

afterEach(() => {
  resetVoiceLibraryAssetFallbackForTests();
  vi.restoreAllMocks();
});

describe('voiceLibraryAssetFallback', () => {
  it('merges direct voice profiles when the aggregate asset response has none', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/voice-library')) {
        return new Response(JSON.stringify({
          assets: [
            {
              id: 'voice-cloning:Maya',
              module: 'voice-cloning',
              type: 'voice_profile',
              storage_path: 'F:/LLM/omnix/resources/voice_clones/Maya.wav',
              metadata: { profile_name: 'Maya' },
            },
          ],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({
        assets: [
          { id: 'image:one', module: 'image', type: 'image' },
        ],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    installVoiceLibraryAssetFallback(fetchImpl as typeof fetch);
    const response = await window.fetch('/api/assets');
    const body = await response.json() as { assets: Array<{ id: string; type: string }> };

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(body.assets.map((asset) => asset.id)).toEqual(['image:one', 'voice-cloning:Maya']);
    expect(response.headers.get('x-omnix-voice-library-merged')).toBe('true');
  });

  it('merges missing direct voices even when aggregate assets already include a partial voice list', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/voice-library')) {
        return new Response(JSON.stringify({
          assets: [
            {
              id: 'voice-cloning:Maya',
              module: 'voice-cloning',
              type: 'voice_profile',
              metadata: { voice_clone_id: 'Maya', canonical: true },
            },
            {
              id: 'voice-cloning:Jinx',
              module: 'voice-cloning',
              type: 'voice_profile',
              metadata: { voice_clone_id: 'Jinx', canonical: true },
            },
          ],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({
        assets: [
          {
            id: 'voice-cloning:Maya',
            module: 'voice-cloning',
            type: 'voice_profile',
            metadata: { voice_clone_id: 'maya', canonical: false },
          },
          { id: 'image:one', module: 'image', type: 'image' },
        ],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    installVoiceLibraryAssetFallback(fetchImpl as typeof fetch);
    const response = await window.fetch('/api/assets');
    const body = await response.json() as {
      assets: Array<{ id: string; metadata?: { voice_clone_id?: string; canonical?: boolean } }>;
    };

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(body.assets.map((asset) => asset.id)).toEqual([
      'voice-cloning:Maya',
      'image:one',
      'voice-cloning:Jinx',
    ]);
    expect(body.assets[0]?.metadata).toEqual({ voice_clone_id: 'Maya', canonical: true });
    expect(response.headers.get('x-omnix-voice-library-merged')).toBe('true');
  });

  it('preserves the aggregate response when the direct endpoint is unavailable', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/voice-library')) {
        return new Response('not found', { status: 404 });
      }
      return new Response(JSON.stringify({
        assets: [{ id: 'image:one', module: 'image', type: 'image' }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    installVoiceLibraryAssetFallback(fetchImpl as typeof fetch);
    const response = await window.fetch('/api/assets');
    const body = await response.json() as { assets: Array<{ id: string }> };

    expect(response.status).toBe(200);
    expect(body.assets.map((asset) => asset.id)).toEqual(['image:one']);
  });
});
