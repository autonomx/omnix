import { describe, expect, it } from 'vitest';
import { chartPalette } from '../../chartPalette';
import { alertLevelPriceAtBar } from './alertLevels';
import { drawingToolDefinition } from './registry';
import { pointAt, runTool } from './testing';
import type { DrawingShape } from './types';

function only<K extends DrawingShape['kind']>(shapes: DrawingShape[], kind: K): Extract<DrawingShape, { kind: K }>[] {
  return shapes.filter((shape): shape is Extract<DrawingShape, { kind: K }> => shape.kind === kind);
}

describe('drawing tool geometry and hit tests', () => {
  it('dot: one marker that grows when selected', () => {
    const { shapes, hit } = runTool('dot', [[100, 200]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'marker', x: 100, y: 200, radius: 4, className: 'drawing-dot' })]);
    expect(runTool('dot', [[100, 200]], { selected: true }).shapes[0]).toMatchObject({ radius: 5, stroke: chartPalette.yellow, className: 'drawing-dot selected' });
    expect(hit(103, 200)).not.toBeNull();
    expect(hit(120, 200)).toBeNull();
  });

  it('horizontal line spans the viewport at the anchor price', () => {
    const { shapes, hit } = runTool('horizontal-line', [[100, 200]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'segment', x1: 0, y1: 200, x2: 800, y2: 200, stroke: '#66d9e8', strokeWidth: 2 })]);
    expect(hit(10, 203)).not.toBeNull();
    expect(hit(10, 220)).toBeNull();
  });

  it('horizontal ray starts at the anchor and runs right', () => {
    const { shapes, hit } = runTool('horizontal-ray', [[100, 200]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'segment', x1: 100, y1: 200, x2: 800, y2: 200 })]);
    expect(hit(500, 200)).not.toBeNull();
    expect(hit(50, 200)).toBeNull();
  });

  it('vertical line spans the viewport height', () => {
    const { shapes, hit } = runTool('vertical-line', [[100, 200]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'segment', x1: 100, y1: 0, x2: 100, y2: 600 })]);
    expect(hit(102, 550)).not.toBeNull();
    expect(hit(140, 550)).toBeNull();
  });

  it('crossline draws both lines through the anchor', () => {
    const { shapes, hit } = runTool('crossline', [[100, 200]]);
    expect(shapes).toEqual([
      expect.objectContaining({ kind: 'segment', x1: 0, y1: 200, x2: 800, y2: 200 }),
      expect.objectContaining({ kind: 'segment', x1: 100, y1: 0, x2: 100, y2: 600 }),
    ]);
    expect(hit(700, 201)).not.toBeNull();
    expect(hit(100, 500)).not.toBeNull();
    expect(hit(300, 400)).toBeNull();
  });

  it('trend line joins its anchors, dashed when styled so, and extends on request', () => {
    const { shapes, hit } = runTool('trend-line', [[100, 300], [300, 100]], { style: { lineStyle: 'dashed' }, selected: true });
    expect(shapes).toEqual([expect.objectContaining({ kind: 'segment', x1: 100, y1: 300, x2: 300, y2: 100, dash: [6, 4], className: 'selected' })]);
    expect(hit(200, 200)).not.toBeNull();
    expect(hit(400, 0)).toBeNull();
    const extended = runTool('trend-line', [[100, 300], [300, 100]], { properties: { extendRight: true } });
    expect(extended.shapes[0]).toMatchObject({ x1: 100, y1: 300, x2: 800, y2: -400 });
    expect(extended.hit(400, 0)).not.toBeNull();
  });

  it('ray runs from the first anchor through the second to the viewport edge', () => {
    expect(runTool('ray', [[100, 300], [200, 250]]).shapes[0]).toMatchObject({ x1: 100, y1: 300, x2: 800, y2: -50 });
    expect(runTool('ray', [[300, 300], [200, 250]]).shapes[0]).toMatchObject({ x2: 0, y2: 150 });
    expect(runTool('ray', [[100, 300], [100, 400]]).shapes[0]).toMatchObject({ x2: 100, y2: 600 });
    const { hit } = runTool('ray', [[100, 300], [200, 250]]);
    expect(hit(700, 0)).not.toBeNull();
    expect(hit(50, 325)).toBeNull();
  });

  it('arrow keeps its filled head at the second anchor and a wide tip target', () => {
    const { shapes, hit } = runTool('arrow', [[100, 100], [200, 100]]);
    expect(shapes.map((shape) => shape.kind)).toEqual(['segment', 'polygon', 'marker']);
    const [head] = only(shapes, 'polygon');
    // Six stroke widths long, its tip one stroke width beyond the line end.
    expect(head.points).toEqual([{ x: 190, y: 94 }, { x: 202, y: 100 }, { x: 190, y: 106 }]);
    expect(head.fill).toBe('#66d9e8');
    expect(only(shapes, 'marker')[0]).toMatchObject({ x: 200, y: 100, radius: 11, className: 'drawing-hit-target' });
    expect(hit(208, 108)).not.toBeNull();
    expect(hit(150, 140)).toBeNull();
  });

  it('rectangle is a translucent box between its anchors', () => {
    const { shapes, hit } = runTool('rectangle', [[300, 100], [100, 250]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'rect', x: 100, y: 100, width: 200, height: 150, fill: '#66d9e8', fillOpacity: 0x20 / 0xff })]);
    expect(hit(200, 200)).not.toBeNull();
    expect(hit(400, 200)).toBeNull();
  });

  it('circle uses the larger side as its diameter', () => {
    const { shapes, hit } = runTool('circle', [[100, 100], [300, 150]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'ellipse', cx: 200, cy: 125, rx: 100, ry: 100 })]);
    expect(hit(200, 200)).not.toBeNull();
    expect(hit(200, 240)).toBeNull();
  });

  it('ellipse fits the box between its anchors', () => {
    const { shapes, hit } = runTool('ellipse', [[100, 100], [300, 150]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'ellipse', cx: 200, cy: 125, rx: 100, ry: 25 })]);
    expect(hit(200, 140)).not.toBeNull();
    expect(hit(200, 170)).toBeNull();
  });

  it('fibonacci draws each retracement level with its label', () => {
    const { shapes, hit } = runTool('fibonacci', [[100, 100], [300, 300]]);
    const lines = only(shapes, 'segment');
    const labels = only(shapes, 'text');
    expect(lines.map((line) => line.y1)).toEqual([100, 147.2, 176.4, 200, 223.6, 257.2, 300].map((value) => expect.closeTo(value, 6)));
    expect(lines[0]).toMatchObject({ x1: 100, x2: 300 });
    expect(labels.map((label) => label.text)).toEqual(['0', '0.236', '0.382', '0.5', '0.618', '0.786', '1']);
    expect(labels[3]).toMatchObject({ x: 304, y: 198 });
    expect(shapes.map((shape) => shape.kind).slice(0, 4)).toEqual(['segment', 'text', 'segment', 'text']);
    expect(hit(150, 200)).not.toBeNull();
    expect(hit(150, 160)).toBeNull();
    const custom = runTool('fibonacci', [[100, 100], [300, 300]], {
      properties: {
        levels: [{ value: 0, color: '', visible: true }, { value: 0.5, color: '#ff0000', visible: true }, { value: 1, color: '', visible: false }],
        showLabels: false,
      },
    });
    expect(custom.shapes.map((shape) => shape.kind)).toEqual(['segment', 'segment']);
    expect(custom.shapes[1]).toMatchObject({ y1: 200, stroke: '#ff0000' });
    // A stored value of another shape is kept, and geometry falls back to the default levels.
    expect(only(runTool('fibonacci', [[100, 100], [300, 300]], { properties: { levels: 'broken' } }).shapes, 'segment')).toHaveLength(7);
  });

  it('text shows the drawing text or the default note', () => {
    const { shapes, hit } = runTool('text', [[100, 100]]);
    expect(shapes).toEqual([expect.objectContaining({ kind: 'text', x: 100, y: 100, text: 'Market note' })]);
    expect(runTool('text', [[100, 100]], { text: 'Breakout' }).shapes[0]).toMatchObject({ text: 'Breakout' });
    expect(drawingToolDefinition('text')?.defaultText).toBe('Market note');
    expect(hit(120, 96)).not.toBeNull();
    expect(hit(100, 140)).toBeNull();
  });

  it('measurement keeps its area, guides, arrow and price/percent/bars label', () => {
    const { shapes, hit } = runTool('measurement', [[100, 300], [220, 200]], { interval: '1m' });
    expect(shapes.map((shape) => shape.kind)).toEqual(['rect', 'segment', 'segment', 'segment', 'polyline', 'rect', 'text']);
    expect(shapes[0]).toMatchObject({ x: 100, y: 200, width: 120, height: 100, fill: chartPalette.drawingBlue, fillOpacity: 0.14 });
    const label = only(shapes, 'text')[0];
    // 700 -> 800 is +100 (+14.29%) over 120 one-minute bars.
    expect(label.text).toBe('100 (14.29%) 120');
    expect(label).toMatchObject({ x: 160, y: 179, align: 'middle' });
    // The label box is at least 126px wide, 7.2px per character plus padding.
    expect(shapes[5]).toMatchObject({ x: 160 - 133.2 / 2, y: 160, width: 133.2, height: 30 });
    expect(shapes.slice(1, 5).every((shape) => shape.hit === 'none')).toBe(true);
    expect(drawingToolDefinition('measurement')).toMatchObject({ draftPreview: 'shapes', handleClassName: 'trading-measurement-handle' });
    expect(hit(150, 250)).not.toBeNull();
    expect(hit(400, 250)).toBeNull();
    expect(runTool('measurement', [[100, 300], [220, 200]], { style: { color: '#ff0000' } }).shapes[0]).toMatchObject({ fill: '#ff0000' });
  });

  it('returns no shapes until every anchor exists', () => {
    expect(runTool('trend-line', [[100, 100]]).shapes).toEqual([]);
  });
});

describe('drawing alert levels', () => {
  // Bar index of a time on the test projector: one bar per pixel/minute.
  const barIndex = (time: string) => (Date.parse(time) - Date.parse(pointAt(0, 0).time)) / 60_000;
  const priceAt = (level: Parameters<typeof alertLevelPriceAtBar>[0], index: number) => alertLevelPriceAtBar(level, index, barIndex);

  it('horizontal line and ray alert at their price, the ray only from its anchor', () => {
    const anchor = pointAt(100, 200);
    const [line] = drawingToolDefinition('horizontal-line')!.alertLevels!([anchor], {});
    expect(line).toEqual({ key: 'line', label: 'Horizontal line', anchors: [anchor], extend: { left: true, right: true }, interpolation: 'bars' });
    expect(priceAt(line, 0)).toBe(800);
    expect(priceAt(line, 900)).toBe(800);
    const [ray] = drawingToolDefinition('horizontal-ray')!.alertLevels!([anchor], {});
    expect(ray.extend).toEqual({ left: false, right: true });
    expect(priceAt(ray, 50)).toBeNull();
    expect(priceAt(ray, 900)).toBe(800);
  });

  it('trend line alerts between its anchors in bar space unless extended', () => {
    const points = [pointAt(200, 200), pointAt(100, 300)];
    const definition = drawingToolDefinition('trend-line')!;
    const [level] = definition.alertLevels!(points, { extendLeft: false, extendRight: false });
    // Anchors come back ordered by time.
    expect(level.anchors).toEqual([pointAt(100, 300), pointAt(200, 200)]);
    expect(level.interpolation).toBe('bars');
    expect(priceAt(level, 150)).toBeCloseTo(750);
    expect(priceAt(level, 250)).toBeNull();
    const [extended] = definition.alertLevels!(points, { extendLeft: false, extendRight: true });
    expect(priceAt(extended, 300)).toBeCloseTo(900);
    expect(priceAt(extended, 50)).toBeNull();
  });

  it('ray alerts from its first anchor in the direction of the second', () => {
    const definition = drawingToolDefinition('ray')!;
    const [right] = definition.alertLevels!([pointAt(100, 300), pointAt(200, 200)], {});
    expect(priceAt(right, 50)).toBeNull();
    expect(priceAt(right, 400)).toBeCloseTo(1000);
    const [left] = definition.alertLevels!([pointAt(200, 300), pointAt(100, 200)], {});
    expect(priceAt(left, 250)).toBeNull();
    expect(priceAt(left, 0)).toBeCloseTo(900);
    expect(definition.alertLevels!([pointAt(100, 300), pointAt(100, 200)], {})).toEqual([]);
  });

  it('interpolates by bar index, not by time, across gaps', () => {
    // An overnight gap: bar 1 is a day after bar 0, so time and bar index disagree.
    const times = ['2026-10-05T19:55:00.000Z', '2026-10-06T13:30:00.000Z', '2026-10-06T13:35:00.000Z'];
    const indexOf = (time: string) => times.indexOf(time);
    const [level] = drawingToolDefinition('trend-line')!.alertLevels!(
      [{ time: times[0], price: 100 }, { time: times[2], price: 110 }],
      { extendLeft: false, extendRight: false },
    );
    expect(alertLevelPriceAtBar(level, 1, indexOf)).toBe(105);
  });
});
