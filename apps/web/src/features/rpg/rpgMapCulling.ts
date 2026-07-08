import type {
  RpgMapBounds,
  RpgMapLabelDefinition,
  RpgMapMarker,
  RpgMapObjectDefinition,
  RpgMapRouteGeometry,
} from '../../api/rpgMapClient';
import type { RpgMapViewportState } from './rpgMapViewport';

export interface RpgMapVisibleSet {
  bounds: RpgMapBounds;
  labels: RpgMapLabelDefinition[];
  markers: RpgMapMarker[];
  objects: RpgMapObjectDefinition[];
  routes: RpgMapRouteGeometry[];
}

export function cullRpgMapContent(
  mapBounds: RpgMapBounds,
  viewport: RpgMapViewportState,
  objects: RpgMapObjectDefinition[],
  routes: RpgMapRouteGeometry[],
  labels: RpgMapLabelDefinition[],
  markers: RpgMapMarker[],
  overscanRatio = 0.12,
): RpgMapVisibleSet {
  const bounds = visibleLogicalBounds(mapBounds, viewport, overscanRatio);
  return {
    bounds,
    objects: objects.filter((item) => objectIntersects(item, bounds)),
    routes: routes.filter((item) => pointsIntersect(item.points, bounds)),
    labels: labels.filter((item) => pointInBounds(item.x, item.y, bounds)),
    markers: markers.filter((item) => pointInBounds(item.x, item.y, bounds)),
  };
}

export function visibleLogicalBounds(
  mapBounds: RpgMapBounds,
  viewport: RpgMapViewportState,
  overscanRatio = 0.12,
): RpgMapBounds {
  const zoom = Math.max(0.0001, viewport.zoom);
  const rawX = (mapBounds.x - viewport.panX) / zoom;
  const rawY = (mapBounds.y - viewport.panY) / zoom;
  const rawWidth = mapBounds.width / zoom;
  const rawHeight = mapBounds.height / zoom;
  const overscanX = rawWidth * Math.max(0, overscanRatio);
  const overscanY = rawHeight * Math.max(0, overscanRatio);
  const left = Math.max(mapBounds.x, rawX - overscanX);
  const top = Math.max(mapBounds.y, rawY - overscanY);
  const right = Math.min(mapBounds.x + mapBounds.width, rawX + rawWidth + overscanX);
  const bottom = Math.min(mapBounds.y + mapBounds.height, rawY + rawHeight + overscanY);
  return {
    x: left,
    y: top,
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top),
  };
}

function objectIntersects(item: RpgMapObjectDefinition, bounds: RpgMapBounds): boolean {
  const width = item.sprite?.width ?? 480;
  const height = item.sprite?.height ?? 360;
  const left = item.x - width / 2;
  const right = item.x + width / 2;
  const top = item.y - height;
  const bottom = item.y + 120;
  return rectanglesIntersect(left, top, right, bottom, bounds);
}

function pointsIntersect(points: [number, number][], bounds: RpgMapBounds): boolean {
  if (!points.length) return false;
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  return rectanglesIntersect(Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys), bounds);
}

function pointInBounds(x: number, y: number, bounds: RpgMapBounds): boolean {
  return x >= bounds.x && y >= bounds.y && x <= bounds.x + bounds.width && y <= bounds.y + bounds.height;
}

function rectanglesIntersect(left: number, top: number, right: number, bottom: number, bounds: RpgMapBounds): boolean {
  return !(
    right < bounds.x
    || left > bounds.x + bounds.width
    || bottom < bounds.y
    || top > bounds.y + bounds.height
  );
}
