import { useQuery } from '@tanstack/react-query';
import {
  getRpgMapDefinition,
  getRpgMapOverlay,
  type RpgMapDefinition,
  type RpgMapObjectDefinition,
  type RpgMapOverlay,
} from '../../api/rpgMapClient';
import { RpgMapViewportSurface } from './RpgMapViewportSurface';
import './RpgMapSurface.css';

interface RpgMapSurfaceProps {
  mapId: string;
  sessionId: string;
}

export function RpgMapSurface({ mapId, sessionId }: RpgMapSurfaceProps) {
  const definitionQuery = useQuery({
    queryKey: ['feature', 'rpg', 'map-definition', mapId],
    queryFn: () => getRpgMapDefinition(mapId),
    enabled: Boolean(mapId),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const overlayQuery = useQuery({
    queryKey: ['feature', 'rpg', 'map-overlay', sessionId, mapId],
    queryFn: () => getRpgMapOverlay(sessionId, mapId),
    enabled: Boolean(sessionId && mapId),
  });

  if (definitionQuery.isPending || overlayQuery.isPending) {
    return <MapStateMessage title="Loading map" detail="Reading the map definition and current session overlay…" />;
  }
  if (definitionQuery.isError) {
    return <MapStateMessage title="Map definition unavailable" detail={errorMessage(definitionQuery.error)} tone="error" />;
  }
  if (overlayQuery.isError) {
    return <MapStateMessage title="Live map state unavailable" detail={errorMessage(overlayQuery.error)} tone="error" />;
  }

  const definition = definitionQuery.data?.definition;
  const overlay = overlayQuery.data?.overlay;
  if (!definition) {
    return <MapStateMessage title="Empty map definition" detail="The server returned a matching revision without map geometry." />;
  }
  if (!overlay) {
    return <MapStateMessage title="Empty map overlay" detail="The selected session did not return live map state." />;
  }

  return (
    <div className="rpg-map-surface">
      {overlay.availability === 'ready' ? null : (
        <MapStateMessage
          compact
          title="Live position unavailable"
          detail={humanizeReason(overlay.unavailable_reason)}
          tone="warning"
        />
      )}
      <RpgMapViewportSurface definition={definition} overlay={overlay} />
      <div className="rpg-map-surface-meta" aria-label="Map revision information">
        <span>{definition.level}</span>
        <span>Definition {shortRevision(definition.definition_revision)}</span>
        <span>Overlay {overlay.overlay_revision}</span>
        <span>Turn {overlay.session_turn_index}</span>
      </div>
      <AccessibleObjectList definition={definition} overlay={overlay} />
    </div>
  );
}

function AccessibleObjectList({ definition, overlay }: { definition: RpgMapDefinition; overlay: RpgMapOverlay }) {
  return (
    <div className="rpg-map-accessible-list" aria-label="Visible map locations">
      <p className="eyebrow">Visible map objects</p>
      <ul>
        {visibleObjects(definition, overlay).map((item) => (
          <li key={item.id}>{item.label || item.location_id || item.id}</li>
        ))}
      </ul>
    </div>
  );
}

function MapStateMessage({
  compact = false,
  detail,
  title,
  tone = 'neutral',
}: {
  compact?: boolean;
  detail: string;
  title: string;
  tone?: 'neutral' | 'warning' | 'error';
}) {
  return (
    <div className={`rpg-map-state-message rpg-map-state-${tone}${compact ? ' rpg-map-state-compact' : ''}`} role="status">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function visibleObjects(definition: RpgMapDefinition, overlay: RpgMapOverlay): RpgMapObjectDefinition[] {
  if (overlay.availability !== 'ready') return definition.objects;
  const visibleIds = new Set(overlay.visible_object_ids);
  return definition.objects.filter((item) => visibleIds.has(item.id));
}

function shortRevision(value: string): string {
  return value.replace(/^sha256:/, '').slice(0, 8) || 'unknown';
}

function humanizeReason(value: string): string {
  return value ? value.replaceAll('_', ' ') : 'The selected session does not expose a valid current map location.';
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The map request failed.';
}
