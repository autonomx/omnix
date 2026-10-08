// Test helpers for drawing tool definitions: a linear projector and a
// geometry runner, so tool tests read in pixels.
import { drawingPropertiesWithDefaults, drawingToolDefinition } from './registry';
import { drawingGeometry, hitTestDrawing } from './scene';
import { DEFAULT_DRAWING_STYLE, type DrawingPoint, type DrawingProperties, type DrawingStyle, type ScreenPoint } from './types';

const BASE_TIME = Date.parse('2026-08-05T00:00:00.000Z');

/** One pixel per minute from 2026-08-05T00:00Z; y = 1000 - price. */
export function testProjector(point: DrawingPoint): ScreenPoint | null {
  const time = Date.parse(point.time);
  return Number.isFinite(time) ? { x: (time - BASE_TIME) / 60_000, y: 1000 - point.price } : null;
}

/** The time/price point that `testProjector` puts at (x, y). */
export function pointAt(x: number, y: number): DrawingPoint {
  return { time: new Date(BASE_TIME + x * 60_000).toISOString(), price: 1000 - y };
}

export function runTool(
  toolId: string,
  pixels: readonly [number, number][],
  options: { properties?: DrawingProperties; style?: Partial<DrawingStyle>; text?: string; selected?: boolean; interval?: string; viewport?: { width: number; height: number } } = {},
) {
  const definition = drawingToolDefinition(toolId);
  if (!definition) throw new Error(`no tool ${toolId}`);
  const result = drawingGeometry({
    definition,
    project: testProjector,
    rawPoints: pixels.map(([x, y]) => pointAt(x, y)),
    viewport: options.viewport ?? { width: 800, height: 600 },
    style: { ...DEFAULT_DRAWING_STYLE, ...options.style },
    properties: drawingPropertiesWithDefaults(toolId, options.properties),
    text: options.text ?? '',
    interval: options.interval ?? '1m',
    selected: options.selected ?? false,
    locked: false,
    draft: false,
  });
  return {
    ...result,
    hit: (x: number, y: number) => (result.context ? hitTestDrawing(definition, result.shapes, result.context, { x, y }) : null),
  };
}
