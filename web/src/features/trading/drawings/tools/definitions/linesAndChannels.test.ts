import { describe, expect, it } from 'vitest';
import { anchoredVolumeWeightedAveragePrice } from '../../../indicators/coreIndicators';
import type { MarketBar } from '../../../tradingTypes';
import { drawingPropertiesWithDefaults, drawingToolDefinition } from '../registry';
import { pointAt, runTool, testServices } from '../testing';
import type { DrawingAlertLevel, DrawingBarSeries, DrawingShape, DrawingToolServices } from '../types';
import { anchoredVwap, regressionFit } from './barTools';
import { moveKeepingWidth } from './channels';

function only<K extends DrawingShape['kind']>(shapes: DrawingShape[], kind: K): Extract<DrawingShape, { kind: K }>[] {
  return shapes.filter((shape): shape is Extract<DrawingShape, { kind: K }> => shape.kind === kind);
}

/** Alert levels as [key, [price at first anchor, price at second anchor], extend]. */
function levels(toolId: string, pixels: [number, number][], properties = {}, services: DrawingToolServices = testServices) {
  const definition = drawingToolDefinition(toolId)!;
  return (definition.alertLevels?.(pixels.map(([x, y]) => pointAt(x, y)), drawingPropertiesWithDefaults(toolId, properties), services) ?? [])
    .map((level: DrawingAlertLevel) => [level.key, level.anchors.map((anchor) => Number(anchor.price.toFixed(6))), level.extend]);
}

const BASE = Date.parse(pointAt(0, 0).time);

/** One-minute bars from the test projector's base time with the given closes (volume 1, high/low one away). */
function bars(closes: readonly number[], volumes?: readonly number[]): DrawingBarSeries {
  return {
    length: closes.length,
    at: (index) => (index >= 0 && index < closes.length
      ? { time: new Date(BASE + index * 60_000).toISOString(), open: closes[index], high: closes[index] + 1, low: closes[index] - 1, close: closes[index], volume: volumes?.[index] ?? 1 }
      : undefined),
    indexAtOrBefore: (time) => Math.min(closes.length - 1, Math.max(-1, Math.floor((Date.parse(time) - BASE) / 60_000))),
  };
}

describe('line variants (TVP-3.1)', () => {
  it('info line shows the price change, bars and angle', () => {
    const { shapes, hit } = runTool('info-line', [[100, 300], [300, 100]]);
    expect(only(shapes, 'segment')).toEqual([expect.objectContaining({ x1: 100, y1: 300, x2: 300, y2: 100 })]);
    expect(only(shapes, 'text')[0].text).toBe('200 (28.57%) · 200 bars · 45°');
    expect(hit(200, 200)).not.toBeNull();
    expect(runTool('info-line', [[100, 300], [300, 100]], { properties: { showLabel: false } }).shapes).toHaveLength(1);
    expect(levels('info-line', [[100, 300], [300, 100]])).toEqual([['line', [700, 900], 'none']]);
  });

  it('extended line runs through both edges and alerts both ways', () => {
    const { shapes, hit } = runTool('extended-line', [[100, 300], [300, 100]]);
    expect(shapes[0]).toMatchObject({ kind: 'segment', x1: 0, y1: 400, x2: 800, y2: -400 });
    expect(hit(20, 380)).not.toBeNull();
    expect(levels('extended-line', [[100, 300], [300, 100]])).toEqual([['line', [700, 900], 'both']]);
  });

  it('trend angle draws the angle from the horizontal, also leftward', () => {
    const right = runTool('trend-angle', [[100, 300], [300, 100]]);
    expect(only(right.shapes, 'text')[0].text).toBe('45°');
    const arc = only(right.shapes, 'polyline')[0].points;
    expect(arc[0].x).toBeGreaterThan(100);
    expect(arc.at(-1)!.y).toBeLessThan(300);
    const left = runTool('trend-angle', [[300, 300], [100, 100]]);
    expect(only(left.shapes, 'text')[0].text).toBe('135°');
    // The arc opens to the left, from the left horizontal up to the line.
    expect(only(left.shapes, 'polyline')[0].points.every((point) => point.x <= 300 + 1e-9)).toBe(true);
    expect(only(left.shapes, 'segment')[1]).toMatchObject({ x1: 300, y1: 300, y2: 300 });
    expect(only(left.shapes, 'segment')[1].x2).toBeLessThan(300);
  });
});

describe('channels (TVP-3.1)', () => {
  it('parallel channel: the third click places the parallel; middle line and fill', () => {
    const { shapes, hit } = runTool('parallel-channel', [[100, 300], [300, 200], [200, 100]]);
    const segments = only(shapes, 'segment');
    expect(segments.map(({ x1, y1, x2, y2 }) => [x1, y1, x2, y2])).toEqual([[100, 300, 300, 200], [100, 150, 300, 50], [100, 225, 300, 125]]);
    expect(segments[2].dash).toEqual([4, 4]);
    expect(only(shapes, 'polygon')).toHaveLength(1);
    expect(hit(200, 100)).not.toBeNull();
    // Two anchors while it is being drawn: the first line only.
    expect(runTool('parallel-channel', [[100, 300], [300, 200]]).shapes).toEqual([]);
    expect(levels('parallel-channel', [[100, 300], [300, 200], [200, 100]])).toEqual([
      ['lower', [700, 800], 'none'],
      ['upper', [850, 950], 'none'],
      ['middle', [775, 875], 'none'],
    ]);
    expect(levels('parallel-channel', [[100, 300], [300, 200], [200, 400]], { extendRight: true, showMiddle: false })).toEqual([
      ['upper', [700, 800], 'right'],
      ['lower', [550, 650], 'right'],
    ]);
  });

  it('parallel channel keeps its width when the first line is dragged', () => {
    const points = [pointAt(100, 300), pointAt(300, 200), pointAt(200, 100)];
    // Width: the third anchor is 150 above the first line at its time (900 against 750).
    const moved = moveKeepingWidth({ points, point: pointAt(100, 200), services: testServices }, 0);
    expect(moved[0]).toMatchObject({ price: 800 });
    // The new line is flat at 800, so the third anchor goes to 950.
    expect(moved[2]).toMatchObject({ time: points[2].time, price: 950 });
  });

  it('flat top/bottom: a trend line and a flat line at the third anchor', () => {
    const { shapes } = runTool('flat-top-bottom', [[100, 300], [300, 200], [200, 400]]);
    expect(only(shapes, 'segment').map(({ x1, y1, x2, y2 }) => [x1, y1, x2, y2])).toEqual([[100, 300, 300, 200], [100, 400, 300, 400]]);
    expect(levels('flat-top-bottom', [[100, 300], [300, 200], [200, 400]])).toEqual([
      ['trend', [700, 800], 'none'],
      ['flat', [600, 600], 'none'],
    ]);
  });

  it('disjoint channel: the second line mirrors the first one\'s slope', () => {
    const { shapes } = runTool('disjoint-channel', [[100, 300], [300, 200], [100, 400]]);
    expect(only(shapes, 'segment').map(({ x1, y1, x2, y2 }) => [x1, y1, x2, y2])).toEqual([[100, 300, 300, 200], [100, 400, 300, 500]]);
    expect(levels('disjoint-channel', [[100, 300], [300, 200], [100, 400]])).toEqual([
      ['first', [700, 800], 'none'],
      ['second', [600, 500], 'none'],
    ]);
  });
});

describe('drawings from bars (TVP-3.1)', () => {
  const line = Array.from({ length: 400 }, (_, index) => 100 + 2 * index);

  it('regression trend fits the closes between its anchors', () => {
    const series = bars(line);
    const fit = regressionFit(series, pointAt(110, 0).time, pointAt(10, 0).time);
    expect(fit).toMatchObject({ first: 10, last: 110, intercept: 120, slope: 2 });
    expect(fit!.deviation).toBeCloseTo(0, 9);
    const noisy = regressionFit(bars(line.map((value, index) => value + (index % 2 ? 1 : -1))), pointAt(10, 0).time, pointAt(110, 0).time);
    expect(noisy!.slope).toBeCloseTo(2, 3);
    expect(noisy!.deviation).toBeCloseTo(1, 3);
    expect(regressionFit(series, pointAt(10, 0).time, pointAt(10, 0).time)).toBeNull();
  });

  it('regression trend draws the fit with deviation bands and alerts on each line', () => {
    const series = bars(line.map((value, index) => value + (index % 2 ? 1 : -1)));
    const { shapes } = runTool('regression-trend', [[10, 0], [110, 0]], { access: { bars: series } });
    const [base, upper, lower] = only(shapes, 'segment');
    expect(base.dash).toEqual([6, 4]);
    expect(base.x1).toBe(10);
    expect(base.x2).toBe(110);
    expect(lower.y1 - upper.y1).toBeCloseTo(4, 2);
    expect(runTool('regression-trend', [[10, 0], [110, 0]]).shapes).toEqual([]);
    const services = { ...testServices, bars: bars(line) };
    expect(levels('regression-trend', [[10, 0], [110, 0]], {}, services)).toEqual([
      ['upper', [120, 320], 'none'],
      ['base', [120, 320], 'none'],
      ['lower', [120, 320], 'none'],
    ]);
  });

  it('anchored VWAP matches the indicator from the first bar at the anchor', () => {
    const closes = Array.from({ length: 50 }, (_, index) => 100 + Math.sin(index) * 5);
    const volumes = closes.map((_, index) => 1 + (index % 7));
    const series = bars(closes, volumes);
    const marketBars = closes.map((close, index) => ({
      start_time: new Date(BASE + index * 60_000).toISOString(), high: String(close + 1), low: String(close - 1), close: String(close), volume: String(volumes[index]),
    })) as unknown as MarketBar[];
    const anchor = new Date(BASE + 10 * 60_000 + 30_000).toISOString();
    const { first, values } = anchoredVwap(series, anchor);
    expect(first).toBe(11);
    expect(values).toEqual(anchoredVolumeWeightedAveragePrice(marketBars, anchor));
    const { shapes } = runTool('anchored-vwap', [[11, 0]], { access: { bars: series } });
    expect(only(shapes, 'polyline')[0].points).toHaveLength(39);
    expect(only(shapes, 'marker')).toHaveLength(1);
  });
});
