import { afterEach, describe, expect, it, vi } from 'vitest';
import { characterAvatarClient } from './characterAvatarClient';

afterEach(() => vi.unstubAllGlobals());

describe('characterAvatarClient optional avatar pack lookup', () => {
  it('returns null through a successful optional lookup instead of issuing an expected 404', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input.toString()).toBe('/api/characters/anaka/avatar-pack/optional');
      return Response.json(null);
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(characterAvatarClient.optionalPack('anaka')).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('returns an existing avatar pack from the optional route', async () => {
    const fetchMock = vi.fn(async () => Response.json({
      character_id: 'anaka',
      version: 1,
      renderer: 'sprite',
      render_mode: 'audio_envelope',
      base_asset_id: 'image:anaka',
      mouth_frames: { closed: 'image:anaka' },
      blink_frames: {},
      expression_frames: {},
      outfit_frames: {},
      background_asset_ids: {},
      rig_asset_id: null,
      created_at: '2026-07-31T00:00:00Z',
      updated_at: '2026-07-31T00:00:00Z',
    }));
    vi.stubGlobal('fetch', fetchMock);

    const pack = await characterAvatarClient.optionalPack('anaka');

    expect(pack?.character_id).toBe('anaka');
    expect(pack?.base_asset_id).toBe('image:anaka');
  });
});

describe('characterAvatarClient avatar generation routing', () => {
  it('routes avatar generation through FLUX and keeps the model loaded', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({
      id: 'avatar-generation:test',
      character_id: 'maya',
      status: 'generating_base',
      request: {},
      base_job_id: 'job:test',
      variant_job_ids: {},
      asset_ids: {},
      error: '',
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    }, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await characterAvatarClient.createGeneration('maya', {
      appearance_prompt: 'Silver hair',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe('/api/characters/maya/avatar-generations');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({
      appearance_prompt: 'Silver hair',
      provider_id: 'image:flux_klein',
      unload_after_generation: false,
    });
  });

  it('preserves explicit residency behavior', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({
      id: 'avatar-generation:test',
      character_id: 'maya',
      status: 'generating_base',
      request: {},
      base_job_id: 'job:test',
      variant_job_ids: {},
      asset_ids: {},
      error: '',
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    }, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await characterAvatarClient.createGeneration('maya', {
      provider_id: 'image:flux_klein',
      unload_after_generation: true,
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      provider_id: 'image:flux_klein',
      unload_after_generation: true,
    });
  });
});
