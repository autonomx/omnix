import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import type { DrawingTool, TradingDrawing } from './drawingCommands';
import { TradingDrawingOverlay, type TradingDrawingOverlayProps } from './TradingDrawingOverlay';
import { pointAt, testProjector } from './tools/testing';

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  // jsdom has no PointerEvent; without it fireEvent drops clientX/clientY.
  vi.stubGlobal('PointerEvent', class extends MouseEvent {
    readonly pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
    }
  });
  Object.assign(Element.prototype, { setPointerCapture: () => undefined });
  vi.spyOn(SVGSVGElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600, toJSON: () => ({}),
  });
});

afterEach(cleanup);

function fakeAdapter() {
  let offset = 0;
  const listeners = new Set<() => void>();
  const adapter = {
    projectDrawingPoint: (point: { time: string; price: number }) => {
      const projected = testProjector(point);
      return projected ? { x: projected.x + offset, y: projected.y } : null;
    },
    drawingPointFromCoordinate: (x: number, y: number) => pointAt(x - offset, y),
    onViewportChange: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    onCrosshair: () => () => undefined,
    indicatorPaneIdAtClientY: () => null,
    indicatorValueFromClientY: () => null,
    zoomAtCoordinate: vi.fn(),
  };
  const pan = (dx: number) => act(() => {
    offset += dx;
    listeners.forEach((listener) => listener());
  });
  return { adapter: adapter as unknown as TradingChartAdapter, pan };
}

function drawing(toolType: TradingDrawing['toolType'], pixels: [number, number][], extra: Partial<TradingDrawing> = {}): TradingDrawing {
  return {
    drawingId: `${toolType}-1`,
    instrumentId: 'fixture',
    toolType,
    points: pixels.map(([x, y]) => pointAt(x, y)),
    selected: false,
    revision: 1,
    ...extra,
  };
}

function renderOverlay(props: Partial<TradingDrawingOverlayProps> & { tool?: DrawingTool } = {}) {
  const { adapter, pan } = fakeAdapter();
  const handlers = {
    onAdd: vi.fn(), onSelect: vi.fn(), onMovePoint: vi.fn(), onTranslateDrawing: vi.fn(), onRemove: vi.fn(),
    onToolComplete: vi.fn(), onAlertAtPoint: vi.fn(), onContextMenu: vi.fn(),
  };
  const view = render(
    <div>
      <TradingDrawingOverlay
        adapter={adapter}
        instrumentId="fixture"
        interval="1m"
        tool="cursor"
        snapMode="none"
        drawings={[]}
        selectedId={null}
        {...handlers}
        {...props}
      />
    </div>,
  );
  const svg = view.container.querySelector('svg')!;
  return { ...view, svg, pan, handlers };
}

describe('TradingDrawingOverlay', () => {
  it('renders each drawing from its tool geometry with selection and lock state', () => {
    const { svg } = renderOverlay({
      drawings: [
        drawing('trend-line', [[100, 300], [200, 200]]),
        drawing('rectangle', [[100, 100], [200, 150]], { drawingId: 'box', locked: true }),
        drawing('measurement', [[300, 300], [400, 200]], { drawingId: 'measure' }),
        drawing('text', [[50, 50]], { drawingId: 'hidden', hidden: true }),
      ],
      selectedId: 'measure',
    });
    const trend = svg.querySelector('g[data-drawing-id="trend-line-1"]')!;
    expect(trend.getAttribute('data-selected')).toBe('false');
    expect(trend.querySelector('line')).toHaveAttribute('x1', '100');
    expect(trend.querySelector('line')).toHaveAttribute('y2', '200');
    expect(svg.querySelector('g[data-drawing-id="box"]')).toHaveAttribute('data-locked', 'true');
    const measure = svg.querySelector('g[data-drawing-id="measure"]')!;
    expect(measure).toHaveAttribute('data-selected', 'true');
    expect(measure.querySelector('.trading-measurement-label-text')?.textContent).toBe('100 (14.29%) 100');
    expect([...measure.querySelectorAll('[data-drawing-point-index]')].map((handle) => handle.getAttribute('class'))).toEqual([
      'trading-measurement-handle', 'trading-measurement-handle',
    ]);
    expect(svg.querySelector('g[data-drawing-id="hidden"]')).toBeNull();
  });

  it('follows the chart viewport by patching the mounted elements', () => {
    const { svg, pan } = renderOverlay({ drawings: [drawing('trend-line', [[100, 300], [200, 200]])], selectedId: 'trend-line-1' });
    const line = svg.querySelector('line')!;
    pan(50);
    expect(svg.querySelector('line')).toBe(line);
    expect(line).toHaveAttribute('x1', '150');
    expect(line).toHaveAttribute('x2', '250');
    expect(svg.querySelector('[data-drawing-point-index="1"]')).toHaveAttribute('cx', '250');
  });

  it('creates a one-click drawing with time/price anchors only', () => {
    const { svg, handlers } = renderOverlay({ tool: 'text' });
    fireEvent.pointerDown(svg, { clientX: 120, clientY: 80, pointerId: 1 });
    expect(handlers.onAdd).toHaveBeenCalledWith(expect.objectContaining({
      toolType: 'text', text: 'Market note', points: [pointAt(120, 80)], properties: {},
    }));
    expect(handlers.onToolComplete).toHaveBeenCalled();
  });

  it('creates a drag drawing and previews it while dragging', () => {
    const { svg, handlers } = renderOverlay({ tool: 'fibonacci' });
    fireEvent.pointerDown(svg, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(svg, { clientX: 200, clientY: 300, pointerId: 1 });
    expect(svg.querySelector('line.draft')).toHaveAttribute('x2', '200');
    fireEvent.pointerUp(svg, { clientX: 200, clientY: 300, pointerId: 1 });
    expect(handlers.onAdd).toHaveBeenCalledWith(expect.objectContaining({
      toolType: 'fibonacci',
      points: [pointAt(100, 100), pointAt(200, 300)],
      properties: expect.objectContaining({ levels: [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] }),
    }));
    expect(svg.querySelector('line.draft')).toBeNull();
  });

  it('previews a measurement with its own shapes', () => {
    const { svg } = renderOverlay({ tool: 'measurement' });
    fireEvent.pointerDown(svg, { clientX: 100, clientY: 300, pointerId: 1 });
    fireEvent.pointerMove(svg, { clientX: 220, clientY: 200, pointerId: 1 });
    expect(svg.querySelector('[data-drawing-draft] .trading-measurement-label-text')?.textContent).toBe('100 (14.29%) 120');
  });

  it('passes trend line anchors to the context menu, and none for other tools', () => {
    const trend = drawing('trend-line', [[100, 300], [200, 200]]);
    const { svg, handlers } = renderOverlay({ drawings: [trend, drawing('rectangle', [[300, 100], [400, 200]], { drawingId: 'box' })] });
    fireEvent.contextMenu(svg.querySelector('g[data-drawing-id="trend-line-1"] line')!, { clientX: 150, clientY: 250 });
    expect(handlers.onContextMenu).toHaveBeenLastCalledWith(expect.objectContaining({
      source: 'context-menu', drawingId: 'trend-line-1', drawingTool: 'trend-line', trendlinePoints: trend.points,
    }), undefined);
    fireEvent.contextMenu(svg.querySelector('g[data-drawing-id="box"] rect')!, { clientX: 350, clientY: 150 });
    expect(handlers.onContextMenu).toHaveBeenLastCalledWith(expect.objectContaining({ drawingId: 'box', trendlinePoints: undefined }), undefined);
  });

  it('erases a drawing with the eraser and selects one with the cursor', () => {
    const erasing = renderOverlay({ tool: 'eraser', drawings: [drawing('dot', [[100, 100]])] });
    fireEvent.pointerDown(erasing.svg.querySelector('circle')!, { clientX: 100, clientY: 100 });
    expect(erasing.handlers.onRemove).toHaveBeenCalledWith('dot-1');
    cleanup();
    const selecting = renderOverlay({ drawings: [drawing('dot', [[100, 100]])] });
    fireEvent.pointerDown(selecting.svg.querySelector('circle')!, { clientX: 100, clientY: 100 });
    expect(selecting.handlers.onSelect).toHaveBeenCalledWith('dot-1');
  });
});
