import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from 'react';
import type { RpgMapDefinition, RpgMapObjectDefinition, RpgMapOverlay } from '../../api/rpgMapClient';
import {
  RPG_MAP_MAX_ZOOM,
  RPG_MAP_MIN_ZOOM,
  RPG_MAP_ZOOM_STEP,
  fitRpgMapViewport,
  panRpgMapViewport,
  rpgMapClientPointToLogical,
  rpgMapKeyboardViewport,
  rpgMapScreenDeltaToLogical,
  rpgMapViewportTransform,
  zoomRpgMapViewportAt,
  type RpgMapViewportState,
} from './rpgMapViewport';

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
const viewportCache = new Map<string, RpgMapViewportState>();

interface PointerPoint {
  x: number;
  y: number;
}

interface PinchStart {
  distance: number;
  midpoint: PointerPoint;
  viewport: RpgMapViewportState;
}

export function RpgMapViewportSurface({ definition, overlay }: { definition: RpgMapDefinition; overlay: RpgMapOverlay }) {
  const { x, y, width, height } = definition.bounds;
  const [viewport, setViewport] = useState<RpgMapViewportState>(() => viewportCache.get(definition.map_id) ?? fitRpgMapViewport());
  const [dragging, setDragging] = useState(false);
  const pointersRef = useRef(new Map<number, PointerPoint>());
  const lastPointRef = useRef<PointerPoint | null>(null);
  const pinchRef = useRef<PinchStart | null>(null);
  const objects = [...definition.objects].sort(compareObjects);
  const visibleIds = new Set(overlay.visible_object_ids);
  const player = overlay.markers.find((marker) => marker.kind === 'player');

  useEffect(() => {
    setViewport(viewportCache.get(definition.map_id) ?? fitRpgMapViewport());
  }, [definition.map_id]);

  useEffect(() => {
    viewportCache.set(definition.map_id, viewport);
  }, [definition.map_id, viewport]);

  const fitMap = () => setViewport(fitRpgMapViewport());
  const zoomBy = (factor: number) => setViewport(
    zoomRpgMapViewportAt(viewport, definition.bounds, viewport.zoom * factor),
  );

  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const anchor = rpgMapClientPointToLogical(event.clientX, event.clientY, rect, definition.bounds);
    setViewport(zoomRpgMapViewportAt(
      viewport,
      definition.bounds,
      viewport.zoom * Math.exp(-event.deltaY * 0.0015),
      anchor.x,
      anchor.y,
    ));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = rpgMapKeyboardViewport(viewport, definition.bounds, event.key, event.shiftKey);
    if (!next) return;
    event.preventDefault();
    setViewport(next);
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    setDragging(true);
    if (pointersRef.current.size === 1) {
      lastPointRef.current = { x: event.clientX, y: event.clientY };
      pinchRef.current = null;
    } else if (pointersRef.current.size === 2) {
      pinchRef.current = createPinchStart(pointersRef.current, viewport);
      lastPointRef.current = null;
    }
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!pointersRef.current.has(event.pointerId)) return;
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const rect = event.currentTarget.getBoundingClientRect();
    if (pointersRef.current.size >= 2) {
      const start = pinchRef.current ?? createPinchStart(pointersRef.current, viewport);
      const current = pinchMetrics(pointersRef.current);
      pinchRef.current = start;
      if (!start || !current || start.distance <= 0) return;
      const anchor = rpgMapClientPointToLogical(start.midpoint.x, start.midpoint.y, rect, definition.bounds);
      const midpointDelta = rpgMapScreenDeltaToLogical(
        current.midpoint.x - start.midpoint.x,
        current.midpoint.y - start.midpoint.y,
        rect,
        definition.bounds,
      );
      const zoomed = zoomRpgMapViewportAt(
        start.viewport,
        definition.bounds,
        start.viewport.zoom * (current.distance / start.distance),
        anchor.x,
        anchor.y,
      );
      setViewport(panRpgMapViewport(zoomed, definition.bounds, midpointDelta.x, midpointDelta.y));
      return;
    }
    const previous = lastPointRef.current;
    if (!previous) {
      lastPointRef.current = { x: event.clientX, y: event.clientY };
      return;
    }
    const delta = rpgMapScreenDeltaToLogical(
      event.clientX - previous.x,
      event.clientY - previous.y,
      rect,
      definition.bounds,
    );
    setViewport(panRpgMapViewport(viewport, definition.bounds, delta.x, delta.y));
    lastPointRef.current = { x: event.clientX, y: event.clientY };
  };

  const finishPointer = (event: PointerEvent<HTMLDivElement>) => {
    pointersRef.current.delete(event.pointerId);
    if (pointersRef.current.size === 1) {
      lastPointRef.current = [...pointersRef.current.values()][0] ?? null;
      pinchRef.current = null;
    } else if (pointersRef.current.size === 0) {
      lastPointRef.current = null;
      pinchRef.current = null;
      setDragging(false);
    }
  };

  return (
    <div className="rpg-map-viewport-shell">
      <div className="rpg-map-viewport-controls" aria-label="Map viewport controls">
        <button aria-label="Zoom out" disabled={viewport.zoom <= RPG_MAP_MIN_ZOOM} onClick={() => zoomBy(1 / RPG_MAP_ZOOM_STEP)} type="button">−</button>
        <span aria-live="polite">{Math.round(viewport.zoom * 100)}%</span>
        <button aria-label="Zoom in" disabled={viewport.zoom >= RPG_MAP_MAX_ZOOM} onClick={() => zoomBy(RPG_MAP_ZOOM_STEP)} type="button">+</button>
        <button onClick={fitMap} type="button">Fit map</button>
        <button onClick={fitMap} type="button">Reset view</button>
      </div>
      <div
        aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown + - Home 0"
        aria-label="Interactive map viewport. Drag to pan, use the mouse wheel or pinch to zoom, and use arrow keys to pan."
        className={`rpg-map-canvas-frame${dragging ? ' rpg-map-canvas-dragging' : ''}`}
        onKeyDown={onKeyDown}
        onPointerCancel={finishPointer}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finishPointer}
        onWheel={onWheel}
        role="region"
        tabIndex={0}
      >
        <svg className="rpg-map-canvas" role="img" aria-label={`${definition.map_id} interactive map`} viewBox={`${x} ${y} ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            <pattern id="rpg-map-parchment-grid" width="320" height="320" patternUnits="userSpaceOnUse">
              <rect width="320" height="320" className="rpg-map-parchment-tile" />
              <path d="M0 160H320M160 0V320" className="rpg-map-parchment-line" />
            </pattern>
            <filter id="rpg-map-object-shadow" x="-20%" y="-20%" width="140%" height="150%">
              <feDropShadow dx="0" dy="24" stdDeviation="18" floodOpacity="0.35" />
            </filter>
          </defs>
          <g data-map-viewport="true" transform={rpgMapViewportTransform(viewport)}>
            <rect x={x} y={y} width={width} height={height} fill="url(#rpg-map-parchment-grid)" />
            <g data-map-layer="structures">
              {objects.map((item) => <MapObjectShape item={item} key={item.id} visible={overlay.availability !== 'ready' || visibleIds.has(item.id)} />)}
            </g>
            {overlay.availability === 'ready' && player ? (
              <g className="rpg-map-player-marker" data-map-layer="markers" transform={`translate(${player.x} ${player.y})`}>
                <circle r="92" />
                <path d="M0-120 72 18 0 86-72 18Z" />
              </g>
            ) : null}
          </g>
        </svg>
      </div>
    </div>
  );
}

function MapObjectShape({ item, visible }: { item: RpgMapObjectDefinition; visible: boolean }) {
  const spriteWidth = item.sprite?.width ?? 480;
  const spriteHeight = item.sprite?.height ?? 360;
  return (
    <g aria-label={item.label || item.id} className={`rpg-map-object rpg-map-object-${item.kind}${visible ? '' : ' rpg-map-object-hidden'}`} data-map-object-id={item.id} filter="url(#rpg-map-object-shadow)" transform={`translate(${item.x} ${item.y})`}>
      <rect height={spriteHeight} rx={Math.min(90, spriteWidth * 0.12)} width={spriteWidth} x={-spriteWidth / 2} y={-spriteHeight} />
      <path d={`M${-spriteWidth / 2} ${-spriteHeight} L0 ${-spriteHeight - 170} L${spriteWidth / 2} ${-spriteHeight} Z`} />
      <text y={90}>{item.label || item.location_id || item.id}</text>
    </g>
  );
}

function compareObjects(left: RpgMapObjectDefinition, right: RpgMapObjectDefinition): number {
  return (LAYER_PRIORITY[left.render_order.layer] ?? 100) - (LAYER_PRIORITY[right.render_order.layer] ?? 100)
    || left.render_order.sort_y - right.render_order.sort_y
    || left.render_order.offset - right.render_order.offset
    || left.id.localeCompare(right.id);
}

function createPinchStart(pointers: Map<number, PointerPoint>, viewport: RpgMapViewportState): PinchStart | null {
  const metrics = pinchMetrics(pointers);
  return metrics ? { ...metrics, viewport } : null;
}

function pinchMetrics(pointers: Map<number, PointerPoint>): Omit<PinchStart, 'viewport'> | null {
  const [first, second] = [...pointers.values()];
  if (!first || !second) return null;
  return {
    distance: Math.hypot(second.x - first.x, second.y - first.y),
    midpoint: { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 },
  };
}
