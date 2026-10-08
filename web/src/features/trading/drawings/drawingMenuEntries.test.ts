import { describe, expect, it, vi } from 'vitest';
import type { TradingDrawing } from './drawingCommands';
import { drawingMenuEntries } from './TradingDrawingOverlay';
import { pointAt, testServices } from './tools/testing';

function drawing(toolType: TradingDrawing['toolType'], pixels: [number, number][]): TradingDrawing {
  return { drawingId: `${toolType}-1`, instrumentId: 'fixture', toolType, points: pixels.map(([x, y]) => pointAt(x, y)), selected: false, revision: 1 };
}

describe('drawing alert levels on the context menu', () => {
  it('offers sloped and flat levels when the chart index is the bars index', () => {
    expect(drawingMenuEntries(drawing('trend-line', [[10, 100], [50, 60]]), testServices).drawingAlertLevels).toHaveLength(1);
    expect(drawingMenuEntries(drawing('horizontal-line', [[10, 100]]), testServices).drawingAlertLevels).toHaveLength(1);
  });

  it('offers only flat levels on brick-type charts, where the server would cross other prices', () => {
    const sloped = drawingMenuEntries(drawing('trend-line', [[10, 100], [50, 60]]), testServices, false);
    expect(sloped.drawingAlertLevels).toBeUndefined();
    expect(sloped.trendlinePoints).toBeUndefined();
    const flatTrend = drawingMenuEntries(drawing('trend-line', [[10, 100], [50, 100]]), testServices, false);
    expect(flatTrend.drawingAlertLevels).toHaveLength(1);
    expect(drawingMenuEntries(drawing('horizontal-line', [[10, 100]]), testServices, false).drawingAlertLevels).toHaveLength(1);
  });
});

describe('a tool that throws', () => {
  it('loses only the feature that failed', async () => {
    const { guardToolCall } = await import('./tools/guard');
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const broken = () => { throw new Error('broken'); };
    expect(guardToolCall('test-tool', 'geometry', broken, [])).toEqual([]);
    expect(guardToolCall('test-tool', 'geometry', broken, [])).toEqual([]);
    expect(guardToolCall('test-tool', 'geometry', () => [1], [])).toEqual([1]);
    expect(error).toHaveBeenCalledTimes(1);
    error.mockRestore();
  });
});
