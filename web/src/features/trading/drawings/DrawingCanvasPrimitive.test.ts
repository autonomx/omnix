import { describe, expect, it, vi } from 'vitest';
import { paintShapes } from './canvasShapes';
import { DrawingCanvasPrimitive, type CanvasDrawingEntry } from './DrawingCanvasPrimitive';
import { runTool } from './tools/testing';
import { drawingToolDefinition } from './tools/registry';

function recordingContext() {
  const calls: string[] = [];
  const state: Record<string, unknown> = {};
  const record = (name: string) => (...args: unknown[]) => {
    calls.push(`${name}(${args.map((arg) => (Array.isArray(arg) ? `[${arg.join(',')}]` : String(arg))).join(',')})`);
  };
  const context = new Proxy(state, {
    get: (target, key: string) => (key in target ? target[key] : record(key)),
    set: (target, key: string, value) => {
      target[key] = value;
      calls.push(`${key}=${String(value)}`);
      return true;
    },
  });
  return { context: context as unknown as CanvasRenderingContext2D, calls };
}

function entry(toolId: string, pixels: [number, number][], drawingId = toolId): CanvasDrawingEntry {
  const { shapes, context } = runTool(toolId, pixels);
  return { drawingId, definition: drawingToolDefinition(toolId)!, shapes, context };
}

describe('canvas drawing renderer', () => {
  it('paints the same shapes as the SVG host: strokes, dashes, fills and text', () => {
    const { context, calls } = recordingContext();
    paintShapes(context, [
      { kind: 'segment', x1: 1, y1: 2, x2: 3, y2: 4, stroke: '#fff', strokeWidth: 2, dash: [6, 4] },
      { kind: 'rect', x: 0, y: 0, width: 10, height: 5, fill: '#66d9e8', fillOpacity: 0.5, radius: 2 },
      { kind: 'text', x: 5, y: 6, text: 'label', align: 'middle', fontSize: 13, fontWeight: 500 },
    ]);
    expect(calls).toEqual(expect.arrayContaining([
      'moveTo(1,2)', 'lineTo(3,4)', 'strokeStyle=#fff', 'lineWidth=2', 'setLineDash([6,4])', 'stroke()',
      'roundRect(0,0,10,5,2)', 'globalAlpha=0.5', 'fillStyle=#66d9e8', 'fill()',
      'font=500 13px sans-serif', 'textAlign=center', 'fillText(label,5,6)',
    ]));
    expect(calls[0]).toBe('save()');
    expect(calls.at(-1)).toBe('restore()');
  });

  it('paints the scene at draw time and hit-tests what it painted, topmost first', () => {
    const primitive = new DrawingCanvasPrimitive();
    const requestUpdate = vi.fn();
    primitive.attached({ requestUpdate } as never);
    const scene = vi.fn(() => [entry('rectangle', [[100, 100], [300, 300]], 'below'), entry('trend-line', [[100, 200], [300, 200]], 'above')]);
    primitive.setScene(scene);
    expect(requestUpdate).toHaveBeenCalledTimes(1);

    const { context, calls } = recordingContext();
    const target = { useMediaCoordinateSpace: (paint: (scope: unknown) => void) => paint({ context, mediaSize: { width: 800, height: 600 } }) };
    const [view] = primitive.paneViews();
    expect(view.zOrder?.()).toBe('top');
    view.renderer()!.draw(target as never);
    expect(scene).toHaveBeenCalledWith({ width: 800, height: 600 });
    expect(calls).toContain('stroke()');

    expect(primitive.hitTest(200, 201)).toMatchObject({ externalId: 'above', cursorStyle: 'pointer', zOrder: 'top' });
    expect(primitive.hitTest(150, 150)).toMatchObject({ externalId: 'below' });
    expect(primitive.hitTest(500, 500)).toBeNull();
    primitive.invalidate();
    expect(requestUpdate).toHaveBeenCalledTimes(2);
    primitive.detached();
    primitive.invalidate();
    expect(requestUpdate).toHaveBeenCalledTimes(2);
  });
});
