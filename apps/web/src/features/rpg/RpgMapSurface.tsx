import { useQuery } from '@tanstack/react-query';
import {
  getRpgMapDefinition,
  getRpgMapOverlay,
  type RpgMapDefinition,
  type RpgMapObjectDefinition,
  type RpgMapOverlay,
} from '../../api/rpgMapClient';
import './RpgMapSurface.css';

interface RpgMapSurfaceProps {
  mapId: string;
  sessionId: string;
}

const LAYER_PRIORITY: Record<string, number> = {
  background: 0,
  terrain: 10,
  routes: 20,
  ground_props: 30,
  structures: 40,
  markers: 50,
  labels: 60,
  fog: 70,
  interaction: 80,
};

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
      <MapCanvas definition={definition} overlay={overlay} />
      <div className="rpg-map-surface-meta" aria-label="Map revision information">
        <span>{definition.level}</span>
        <span>Definition {shortRevision(definition.definition_revision)}</span>
        <span>Overlay {overlay.overlay_revision}</span>
        <span>Turn {overlay.session_turn_index}</span>
      </div>
      <div className="rpg-map-accessible-list" aria-label="Visible map locations">
        <p className="eyebrow">Visible map objects</p>
        <ul>
          {visibleObjects(definition, overlay).map((item) => (
            <li key={item.id}>{item.label || item.location_id || item.id}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function MapCanvas({ definition, overlay }: { definition: RpgMapDefinition; overlay: RpgMapOverlay }) {
  const { x, y, width, height } = definition.bounds;
  const objects = [...definition.objects].sort(compareObjects);
  const visibleIds = new Set(overlay.visible_object_ids);
  const player = overlay.markers.find((marker) => marker.kind === 'player');

  return (
    <div className="rpg-map-canvas-frame">
      <svg
        className="rpg-map-canvas"
        role="img"
        aria-label={`${definition.map_id} interactive map`}
        viewBox={`${x} ${y} ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <pattern id="rpg-map-parchment-grid" width="320" height="320" patternUnits="userSpaceOnUse">
            <rect width="320" height="320" className="rpg-map-parchment-tile" />
            <path d="M0 160H320M160 0V320" className="rpg-map-parchment-line" />
          </pattern>
          <filter id="rpg-map-object-shadow" x="-20%" y="-20%" width="140%" height="150%">
            <feDropShadow dx="0" dy="24" stdDeviation="18" floodOpacity="0.35" />
          </filter>
        </defs>
        <rect x={x} y={y} width={width} height={height} fill="url(#rpg-map-parchment-grid)" />
        <g data-map-layer="structures">
          {objects.map((item) => (
            <MapObjectShape
              item={item}
              key={item.id}
              visible={overlay.availability !== 'ready' || visibleIds.has(item.id)}
            />
          ))}
        </g>
        {overlay.availability === 'ready' && player ? (
          <g
            className="rpg-map-player-marker"
            data-map-layer="markers"
            transform={`translate(${player.x} ${player.y})`}
          >
            <circle r="92" />
            <path d="M0-120 72 18 0 86-72 18Z" />
          </g>
        ) : null}
      </svg>
    </div>
  );
}

function MapObjectShape({ item, visible }: { item: RpgMapObjectDefinition; visible: boolean }) {
  const spriteWidth = item.sprite?.width ?? 480;
  const spriteHeight = item.sprite?.height ?? 360;
  const className = `rpg-map-object rpg-map-object-${item.kind}${visible ? '' : ' rpg-map-object-hidden'}`;
  return (
    <g
      aria-label={item.label || item.id}
      className={className}
      data-map-object-id={item.id}
      filter="url(#rpg-map-object-shadow)"
      transform={`translate(${item.x} ${item.y})`}
    >
      <rect
        height={spriteHeight}
        rx={Math.min(90, spriteWidth * 0.12)}
        width={spriteWidth}
        x={-spriteWidth / 2}
        y={-spriteHeight}
      />
      <path d={`M${-spriteWidth / 2} ${-spriteHeight} L0 ${-spriteHeight - 170} L${spriteWidth / 2} ${-spriteHeight} Z`} />
      <text y={90}>{item.label || item.location_id || item.id}</text>
    </g>
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

function compareObjects(left: RpgMapObjectDefinition, right: RpgMapObjectDefinition): number {
  const leftLayer = LAYER_PRIORITY[left.render_order.layer] ?? 100;
  const rightLayer = LAYER_PRIORITY[right.render_order.layer] ?? 100;
  return leftLayer - rightLayer
    || left.render_order.sort_y - right.render_order.sort_y
    || left.render_order.offset - right.render_order.offset
    || left.id.localeCompare(right.id);
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
