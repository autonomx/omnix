import { describe, expect, it } from 'vitest';
import { drawingToolDefinition, drawingPropertiesWithDefaults } from '../registry';
import { pointAt, runTool, testServices } from '../testing';
import type { DrawingShape } from '../types';

const segments = (shapes: readonly DrawingShape[]) => shapes.filter((shape): shape is Extract<DrawingShape, { kind: 'segment' }> => shape.kind === 'segment');
const texts = (shapes: readonly DrawingShape[]) => shapes.flatMap((shape) => (shape.kind === 'text' ? [shape.text] : []));
const round = (value: number) => Math.round(value * 1000) / 1000;
const alertLevels = (toolId: string, pixels: readonly [number, number][], properties = {}) => {
  const definition = drawingToolDefinition(toolId)!;
  return definition.alertLevels!(pixels.map(([x, y]) => pointAt(x, y)), drawingPropertiesWithDefaults(toolId, properties), testServices);
};

describe('Fibonacci tools (TVP-3.2)', () => {
  it('trend-based fib extension projects A to B from C, and alerts on each visible level', () => {
    // A at price 500, B at 700, C at 600: level 1 is 800 (y 200), level 0.618 is 723.6.
    const { shapes } = runTool('fib-extension', [[100, 500], [200, 300], [300, 400]]);
    const horizontal = segments(shapes).filter((shape) => shape.y1 === shape.y2);
    expect(horizontal.map((shape) => round(shape.y1))).toEqual([400, 352.8, 323.6, 300, 276.4, 242.8, 200, 76.4, -123.6]);
    expect(horizontal[0]).toMatchObject({ x1: 300, x2: 400 });
    expect(texts(shapes)).toContain('1 (800)');
    const levels = alertLevels('fib-extension', [[100, 500], [200, 300], [300, 400]]);
    expect(levels.map((level) => level.key)).toContain('level-1.618');
    expect(levels.find((level) => level.key === 'level-1')?.anchors[0]).toMatchObject({ time: pointAt(300, 0).time, price: 800 });
    expect(levels.every((level) => level.extend === 'right')).toBe(true);
  });

  it('fib time zone draws verticals at the Fibonacci multiples of A-B in bars', () => {
    const { shapes } = runTool('fib-time-zone', [[100, 300], [110, 300]]);
    expect(segments(shapes).map((shape) => round(shape.x1))).toEqual([100, 110, 120, 130, 150, 180, 230, 310, 440, 650]);
    expect(segments(shapes)[0]).toMatchObject({ y1: 0, y2: 600 });
    const zero = runTool('fib-time-zone', [[100, 300], [100, 200]]);
    expect(segments(zero.shapes)).toHaveLength(1);
  });

  it('trend-based fib time measures A-B in bars from C', () => {
    const { shapes } = runTool('fib-time', [[0, 300], [10, 200], [100, 250]], { properties: { levels: [{ value: 0, color: '', visible: true }, { value: 1.618, color: '', visible: true }] } });
    expect(segments(shapes).filter((shape) => shape.y1 === 0).map((shape) => round(shape.x1))).toEqual([100, 116.18]);
  });

  it('fib channel draws parallels at the levels of the width set by C, and alerts on them', () => {
    // Base 100,500 -> 200,400; C one width (price +50) above at A's time.
    const { shapes } = runTool('fib-channel', [[100, 500], [200, 400], [100, 450]], {
      properties: { levels: [{ value: 0, color: '', visible: true }, { value: 1, color: '', visible: true }, { value: 2, color: '', visible: false }] },
    });
    expect(segments(shapes).map((shape) => [shape.x1, shape.y1, shape.x2, shape.y2])).toEqual([[100, 500, 200, 400], [100, 450, 200, 350]]);
    const levels = alertLevels('fib-channel', [[100, 500], [200, 400], [100, 450]]);
    expect(levels.find((level) => level.key === 'level-1')?.anchors.map((anchor) => anchor.price)).toEqual([550, 650]);
  });

  it('fib speed resistance fan draws rays from A through the box divisions', () => {
    const { shapes } = runTool('fib-speed-fan', [[100, 400], [200, 300]]);
    expect(segments(shapes)).toHaveLength(11);
    expect(shapes.some((shape) => shape.kind === 'rect')).toBe(true);
  });

  it('arcs, circles, spiral and wedge scale with their anchors', () => {
    const arcs = runTool('fib-arcs', [[300, 300], [300, 200]]);
    const halves = arcs.shapes.filter((shape) => shape.kind === 'polyline');
    expect(halves).toHaveLength(6);
    // Opening upwards (towards B), the largest arc's top is B.
    const largest = halves[halves.length - 1];
    expect(largest.kind === 'polyline' && Math.min(...largest.points.map((point) => point.y))).toBeCloseTo(200);
    const circles = runTool('fib-circles', [[200, 300], [400, 300]]);
    expect(circles.shapes.filter((shape) => shape.kind === 'ellipse').map((shape) => (shape.kind === 'ellipse' ? round(shape.rx) : 0))).toContain(100);
    const spiral = runTool('fib-spiral', [[300, 300], [350, 300]]);
    expect(spiral.shapes.some((shape) => shape.kind === 'polyline' && shape.points.length > 50)).toBe(true);
    const wedge = runTool('fib-wedge', [[100, 300], [300, 300], [300, 100]]);
    expect(wedge.shapes.filter((shape) => shape.kind === 'polyline')).toHaveLength(6);
    expect(wedge.hit(200, 300)).not.toBeNull();
  });
});

describe('pitchforks and Gann (TVP-3.3)', () => {
  it('pitchfork: median from A through the middle of B-C, tines through B and C', () => {
    const { shapes } = runTool('pitchfork', [[100, 300], [200, 200], [200, 400]]);
    const lines = segments(shapes).map((shape) => [round(shape.x1), round(shape.y1), round(shape.x2), round(shape.y2)]);
    expect(lines).toContainEqual([100, 300, 800, 300]);
    expect(lines).toContainEqual([200, 200, 800, 200]);
    expect(lines).toContainEqual([200, 400, 800, 400]);
    expect(lines).toContainEqual([200, 250, 800, 250]);
    expect(shapes.some((shape) => shape.kind === 'polygon')).toBe(true);
  });

  it('Schiff and modified Schiff move the origin halfway towards B', () => {
    const schiff = segments(runTool('schiff-pitchfork', [[100, 300], [200, 200], [200, 400]]).shapes);
    expect(schiff.some((shape) => shape.x1 === 100 && shape.y1 === 250 && shape.x2 > 200)).toBe(true);
    const modified = segments(runTool('modified-schiff-pitchfork', [[100, 300], [200, 200], [200, 400]]).shapes);
    expect(modified.some((shape) => round(shape.x1) === 150 && round(shape.y1) === 250 && shape.x2 > 200)).toBe(true);
  });

  it('pitchfork alerts on the median and each visible tine, as the lines are drawn', () => {
    const levels = alertLevels('pitchfork', [[100, 300], [200, 200], [200, 400]]);
    expect(levels.map((level) => level.key)).toEqual(['median', 'level-0.5-upper', 'level-0.5-lower', 'level-1-upper', 'level-1-lower']);
    expect(levels[0].anchors.map((anchor) => anchor.price)).toEqual([700, 700]);
    expect(levels.find((level) => level.key === 'level-1-upper')?.anchors.map((anchor) => anchor.price)).toEqual([800, 800]);
    expect(levels.every((level) => level.extend === 'right')).toBe(true);
  });

  it('pitchfan: rays from A through B-C at each level', () => {
    const { shapes } = runTool('pitchfan', [[100, 300], [200, 200], [200, 400]]);
    expect(segments(shapes)).toHaveLength(8);
  });

  it('Gann box: price and time levels across the box; Shift keeps it square', () => {
    const { shapes } = runTool('gann-box', [[100, 100], [300, 300]]);
    expect(segments(shapes)).toHaveLength(14);
    expect(texts(shapes)).toContain('0.618');
    const square = drawingToolDefinition('gann-box')!.constrain!({ x: 300, y: 200 }, [{ x: 100, y: 100 }], { shift: true, alt: false, ctrl: false });
    expect(square).toEqual({ x: 300, y: 300 });
  });

  it('Gann square fixed is always square; Gann square only with Shift', () => {
    const none = { shift: false, alt: false, ctrl: false };
    expect(drawingToolDefinition('gann-square-fixed')!.constrain!({ x: 300, y: 200 }, [{ x: 100, y: 100 }], none)).toEqual({ x: 300, y: 300 });
    expect(drawingToolDefinition('gann-square')!.constrain!({ x: 300, y: 200 }, [{ x: 100, y: 100 }], none)).toEqual({ x: 300, y: 200 });
    const { shapes } = runTool('gann-square', [[100, 100], [300, 300]]);
    expect(shapes.filter((shape) => shape.kind === 'polyline')).toHaveLength(4);
  });

  it('Gann fan: nine angles, 1x1 through B', () => {
    const { shapes } = runTool('gann-fan', [[100, 400], [200, 300]]);
    const rays = segments(shapes);
    expect(rays).toHaveLength(9);
    const oneByOne = rays[4];
    // Through B: the 1x1 ray keeps B's slope.
    expect((oneByOne.y2 - oneByOne.y1) / (oneByOne.x2 - oneByOne.x1)).toBeCloseTo(-1);
    expect(texts(shapes)).toEqual(['1x8', '1x4', '1x3', '1x2', '1x1', '2x1', '3x1', '4x1', '8x1']);
  });
});
