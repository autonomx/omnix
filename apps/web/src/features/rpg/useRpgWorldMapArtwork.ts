import { useQuery } from '@tanstack/react-query';
import { omnixApiClient } from '../../api/client';
import { rpgWorldImageClient } from '../../api/rpgWorldImageClient';
import {
  rpgCurrentLocationIdFromSession,
  rpgWorldIdFromSession,
  rpgWorldMapArtworkAssetId,
} from './rpgWorldMapArtwork';

interface UseRpgWorldMapArtworkOptions {
  locationId?: string | null;
  mapId: string;
  mapLevel?: string | null;
  sessionId: string;
}

export function useRpgWorldMapArtwork({
  locationId,
  mapId,
  mapLevel,
  sessionId,
}: UseRpgWorldMapArtworkOptions) {
  const normalizedSessionId = sessionId.trim();
  const normalizedMapId = mapId.trim();
  const sessionQuery = useQuery({
    queryKey: ['feature', 'rpg', 'session', normalizedSessionId],
    queryFn: () => omnixApiClient.getRpgSession(normalizedSessionId),
    enabled: Boolean(normalizedSessionId),
  });
  const session = sessionQuery.data?.session;
  const worldId = rpgWorldIdFromSession(session);
  const currentLocationId = locationId?.trim() || rpgCurrentLocationIdFromSession(session);
  const targetsQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-image-targets', worldId],
    queryFn: () => rpgWorldImageClient.list(worldId),
    enabled: Boolean(worldId),
    staleTime: 30_000,
  });
  const assetId = normalizedMapId
    ? rpgWorldMapArtworkAssetId({
      locationId: currentLocationId,
      mapId: normalizedMapId,
      mapLevel,
      targets: targetsQuery.data?.targets ?? [],
    })
    : null;

  return {
    assetId,
    currentLocationId,
    isFetching: sessionQuery.isFetching || targetsQuery.isFetching,
    worldId,
  };
}
