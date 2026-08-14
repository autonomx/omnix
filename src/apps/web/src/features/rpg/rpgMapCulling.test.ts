import { describe, expect, it } from 'vitest';
import type { RpgMapLabelDefinition, RpgMapMarker, RpgMapObjectDefinition, RpgMapRouteGeometry } from '../../api/rpgMapClient';
import { cullRpgMapContent, visibleLogicalBounds } from './rpgMapCulling';

const bounds = { x: 0, y: 0, width: 1000, height: 600 };
const object = (id: string, x: number, y: number): RpgMapObjectDefinition => ({
  id, kind: 'building', x, y, anchor: 'bottom_center', label: id, description: '', tags: [],
  render_order: { layer: 'structures', sort_y: y, offset: 0 }, sprite: { asset_id: `asset:${id}`, width: 100, height: 100 },
});
const marker = (id: string, x: number, y: number): RpgMapMarker => ({ id, kind: 'event', label: id, x, y });
const label = (id: string, x: number, y: number): RpgMapLabelDefinition => ({ id, text: id, x, y, priority: 0 });
const route = (id: string, points: [number, number][]): RpgMapRouteGeometry => ({ route_id: id, style: 'road', points });

describe('rpgMapCulling', () => {
  it('returns the full map at fitted zoom', () => {
    expect(visibleLogicalBounds(bounds, { zoom: 1, panX: 0, panY: 0 }, 0)).toEqual(bounds);
  });

  it('culls offscreen objects, routes, labels, and markers after zoom and pan', () => {
    const result = cullRpgMapContent(
      bounds,
      { zoom: 2, panX: -1000, panY: -600 },
      [object('left', 100, 100), object('right', 800, 450)],
      [route('left-road', [[20, 20], [200, 100]]), route('right-road', [[700, 400], [950, 550]])],
      [label('left-label', 120, 120), label('right-label', 850, 500)],
      [marker('left-marker', 100, 100), marker('right-marker', 900, 520)],
      0,
    );

    expect(result.bounds).toEqual({ x: 500, y: 300, width: 500, height: 300 });
    expect(result.objects.map((item) => item.id)).toEqual(['right']);
    expect(result.routes.map((item) => item.route_id)).toEqual(['right-road']);
    expect(result.labels.map((item) => item.id)).toEqual(['right-label']);
    expect(result.markers.map((item) => item.id)).toEqual(['right-marker']);
  });

  it('uses overscan to retain near-edge sprites and route segments', () => {
    const result = cullRpgMapContent(
      bounds,
      { zoom: 2, panX: -1000, panY: -600 },
      [object('near-edge', 470, 300), object('far', 200, 100)],
      [route('near-route', [[470, 310], [520, 330]])],
      [],
      [],
      0.1,
    );

    expect(result.objects.map((item) => item.id)).toEqual(['near-edge']);
    expect(result.routes.map((item) => item.route_id)).toEqual(['near-route']);
  });

  it('keeps deterministic source order for stable SVG output', () => {
    const objects = [object('b', 700, 400), object('a', 650, 350)];
    const result = cullRpgMapContent(bounds, { zoom: 1, panX: 0, panY: 0 }, objects, [], [], []);

    expect(result.objects.map((item) => item.id)).toEqual(['b', 'a']);
  });
});
