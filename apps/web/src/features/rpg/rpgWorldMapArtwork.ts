import type { RpgWorldImageTarget } from '../../api/rpgWorldImageClient';

interface RpgWorldMapArtworkSelection {
  locationId?: string | null;
  mapId: string;
  mapLevel?: string | null;
  targets: RpgWorldImageTarget[];
}

export function rpgWorldIdFromSession(value: unknown): string {
  const session = recordValue(value);
  const state = recordValue(session.state);
  const manifest = recordValue(session.manifest);
  const publishedWorld = recordValue(state.published_world);
  const worldBinding = recordValue(state.world_binding);
  const setupBinding = recordValue(recordValue(session.setup_payload).published_world_binding);
  return firstText(
    manifest.world_id,
    publishedWorld.world_id,
    worldBinding.world_id,
    setupBinding.world_id,
  );
}

export function rpgCurrentLocationIdFromSession(value: unknown): string {
  const session = recordValue(value);
  const state = recordValue(session.state);
  const runtime = recordValue(session.runtime_state);
  const simulation = recordValue(session.simulation_state);
  const mapState = recordValue(state.map_state);
  const world = recordValue(state.world);
  return firstText(
    mapState.current_location_id,
    state.current_location_id,
    world.current_location_id,
    runtime.current_location_id,
    simulation.current_location_id,
  );
}

export function rpgMapLevelFromId(mapId: string): string {
  const normalized = mapId.trim().toLowerCase();
  if (normalized.startsWith('region:') || normalized.startsWith('world:')) return 'region';
  if (normalized.startsWith('settlement:')) return 'settlement';
  if (normalized.startsWith('location:')) return 'location';
  if (normalized.startsWith('interior:')) return 'interior';
  return '';
}

export function rpgGeneratedMapLocationId(mapId: string): string {
  for (const prefix of ['settlement:generated:', 'location:generated:', 'interior:generated:']) {
    if (mapId.startsWith(prefix)) return mapId.slice(prefix.length).trim();
  }
  return '';
}

export function rpgWorldMapArtworkAssetId({
  locationId,
  mapId,
  mapLevel,
  targets,
}: RpgWorldMapArtworkSelection): string | null {
  const normalizedMapId = mapId.trim();
  const normalizedLevel = (mapLevel?.trim() || rpgMapLevelFromId(normalizedMapId)).toLowerCase();
  const inferredLocationId = rpgGeneratedMapLocationId(normalizedMapId);
  const effectiveLocationId = inferredLocationId || locationId?.trim() || '';
  const locationMapTargets = targets.filter((target) => (
    target.review_state === 'approved'
    && Boolean(target.active_asset_id)
    && textValue(target.metadata.map_level).toLowerCase() === 'location'
  ));

  const mapIdTarget = locationMapTargets.find((target) => {
    const metadata = target.metadata;
    return [metadata.map_id, metadata.definition_map_id, metadata.source_map_id]
      .some((value) => textValue(value) === normalizedMapId);
  });
  if (mapIdTarget?.active_asset_id) return mapIdTarget.active_asset_id;

  if (!['region', 'world'].includes(normalizedLevel) && effectiveLocationId) {
    const locationTarget = locationMapTargets.find((target) => target.entity_id === effectiveLocationId);
    if (locationTarget?.active_asset_id) return locationTarget.active_asset_id;
  }

  const worldTarget = targets.find((target) => (
    target.target_id === 'world:map'
    && target.review_state !== 'rejected'
    && Boolean(target.active_asset_id)
  ));
  return worldTarget?.active_asset_id ?? null;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const text = textValue(value);
    if (text) return text;
  }
  return '';
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}
