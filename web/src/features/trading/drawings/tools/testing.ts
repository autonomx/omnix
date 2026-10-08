// Test helpers for drawing tool definitions: a linear projector and a
// geometry runner, so tool tests read in pixels.
import { drawingPropertiesWithDefaults, drawingToolDefinition } from './registry';
import { drawingGeometry, hitTestDrawing, staticChartAccess } from './scene';
import { DEFAULT_DRAWING_STYLE, type DrawingChartAccess, type DrawingToolServices, type DrawingPoint, type DrawingProperties, type DrawingStyle, type ScreenPoint } from './types';

const BASE_TIME = Date.parse('2026-08-05T00:00:00.000Z');

/** One pixel per minute from 2026-08-05T00:00Z; y = 1000 - price. */
export function testProjector(point: DrawingPoint): ScreenPoint | null {
  const time = Date.parse(point.time);
  return Number.isFinite(time) ? { x: (time - BASE_TIME) / 60_000, y: 1000 - point.price } : null;
}

/** Chart services matching `testProjector`: one bar per minute from the same base time. */
export const testServices: DrawingToolServices = staticChartAccess(testProjector, {
  barIndexForTime: (time) => {
    const at = Date.parse(time);
    return Number.isFinite(at) ? (at - BASE_TIME) / 60_000 : null;
  },
  timeForBarIndex: (index) => new Date(BASE_TIME + index * 60_000).toISOString(),
  timeAfterBars: (time, count) => new Date(Date.parse(time) + count * 60_000).toISOString(),
});

/** The time/price point that `testProjector` puts at (x, y). */
export function pointAt(x: number, y: number): DrawingPoint {
  return { time: new Date(BASE_TIME + x * 60_000).toISOString(), price: 1000 - y };
}

export function runTool(
  toolId: string,
  pixels: readonly [number, number][],
  options: { access?: Partial<DrawingChartAccess>; properties?: DrawingProperties; style?: Partial<DrawingStyle>; text?: string; selected?: boolean; interval?: string; viewport?: { width: number; height: number } } = {},
) {
  const definition = drawingToolDefinition(toolId);
  if (!definition) throw new Error(`no tool ${toolId}`);
  const result = drawingGeometry({
    definition,
    ...staticChartAccess(testProjector, testServices),
    ...options.access,
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
