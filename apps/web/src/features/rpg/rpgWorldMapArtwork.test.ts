import { describe, expect, it } from 'vitest';
import type { RpgWorldImageTarget } from '../../api/rpgWorldImageClient';
import {
  rpgCurrentLocationIdFromSession,
  rpgWorldIdFromSession,
  rpgWorldMapArtworkAssetId,
} from './rpgWorldMapArtwork';

function target(overrides: Partial<RpgWorldImageTarget>): RpgWorldImageTarget {
  return {
    world_id: 'world:test',
    target_id: 'world:map',
    target_type: 'world',
    entity_id: 'world:test',
    role: 'map',
    source_content_hash: 'hash',
    status: 'completed',
    review_state: 'approved',
    suggested_prompt: 'map',
    active_asset_id: 'asset:world-map',
    latest_job_id: null,
    metadata: {},
    attempts: [],
    created_at: '2026-07-31T00:00:00Z',
    updated_at: '2026-07-31T00:00:00Z',
    ...overrides,
  };
}

describe('RPG generated world map artwork', () => {
  it('reads the published world and current location from the live session', () => {
    const session = {
      manifest: { world_id: 'world:tidebreak' },
      state: {
        map_state: { current_location_id: 'tidebreak_docks' },
      },
    };

    expect(rpgWorldIdFromSession(session)).toBe('world:tidebreak');
    expect(rpgCurrentLocationIdFromSession(session)).toBe('tidebreak_docks');
  });

  it('uses the generated world atlas for region maps', () => {
    const assetId = rpgWorldMapArtworkAssetId({
      locationId: 'tidebreak_docks',
      mapId: 'region:generated:northern_pass',
      mapLevel: 'region',
      targets: [
        target({}),
        target({
          target_id: 'map:location:tidebreak_docks',
          target_type: 'location',
          entity_id: 'tidebreak_docks',
          active_asset_id: 'asset:tidebreak-local-map',
          metadata: { map_level: 'location' },
        }),
      ],
    });

    expect(assetId).toBe('asset:world-map');
  });

  it('uses the approved generated local map for generated settlement views', () => {
    const assetId = rpgWorldMapArtworkAssetId({
      locationId: 'unrelated_room',
      mapId: 'settlement:generated:tidebreak_docks',
      mapLevel: 'settlement',
      targets: [
        target({}),
        target({
          target_id: 'map:location:tidebreak_docks',
          target_type: 'location',
          entity_id: 'tidebreak_docks',
          active_asset_id: 'asset:tidebreak-local-map',
          metadata: { map_level: 'location' },
        }),
      ],
    });

    expect(assetId).toBe('asset:tidebreak-local-map');
  });
});
