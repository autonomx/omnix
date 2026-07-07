import type { RpgMapDefinition, RpgMapOverlay } from '../../api/rpgMapClient';

export function RpgMapViewportSurface({ definition }: { definition: RpgMapDefinition; overlay: RpgMapOverlay }) {
  return <div>{definition.map_id}</div>;
}
