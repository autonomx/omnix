import { useCallback, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import type { CoreIndicatorId } from '../indicators/coreIndicators';
import type { TradingAlertIndicatorId } from '../tradingTypes';
import {
  DEFAULT_DRAWING_STYLE,
  snapDrawingPoint,
  type DrawingPoint,
  type DrawingSnapMode,
  type DrawingTool,
  type TradingDrawing,
} from './drawingCommands';
import { ShapeElement, patchShapeElement, svgPoints } from './svgShapes';
import { drawingPropertiesWithDefaults, drawingToolDefinition, isDrawingToolId } from './tools/registry';
import { drawingGeometry, type DrawingProjector } from './tools/scene';
import { shapeSignature } from './tools/shapes';
import { handleIndices, type DrawingGeometryContext, type DrawingShape, type DrawingToolDefinition, type ScreenPoint } from './tools/types';
import { previewPoints, useDrawingEditing, type HandlePreview, type TranslationPreview } from './useDrawingEditing';
import { useDrawingCreation, type PointerPoint } from './useDrawingCreation';
import './TradingDrawingMeasurement.css';

export type ChartAlertPlacement = DrawingPoint & {
  x: number;
  y: number;
  source: 'tool' | 'context-menu';
  indicatorId?: TradingAlertIndicatorId;
  indicatorPeriod?: number;
  drawingId?: string;
  drawingTool?: DrawingTool;
  trendlinePoints?: DrawingPoint[];
};

type Viewport = { width: number; height: number };

type DrawingFrame = {
  drawings: TradingDrawing[];
  selectedId: string | null;
  interval: string;
  handlePreview: HandlePreview | null;
  translationPreview: TranslationPreview | null;
};

type RenderedDrawing = {
  drawing: TradingDrawing;
  definition: DrawingToolDefinition;
  rawPoints: DrawingPoint[];
  shapes: DrawingShape[];
  context: DrawingGeometryContext | null;
  selected: boolean;
};

/** Runs a drawing's tool geometry for the current chart projection. Unknown tools render nothing. */
function renderDrawing(drawing: TradingDrawing, frame: DrawingFrame, project: DrawingProjector, viewport: Viewport): RenderedDrawing | null {
  const definition = drawingToolDefinition(drawing.toolType);
  if (!definition) return null;
  const rawPoints = previewPoints(drawing, frame.translationPreview, frame.handlePreview);
  const selected = drawing.drawingId === frame.selectedId;
  const { shapes, context } = drawingGeometry({
    definition,
    project,
    rawPoints,
    viewport,
    style: drawing.style ?? DEFAULT_DRAWING_STYLE,
    properties: drawingPropertiesWithDefaults(drawing.toolType, drawing.properties),
    text: drawing.text ?? '',
    interval: frame.interval,
    selected,
    locked: drawing.locked ?? false,
    draft: false,
  });
  return { drawing, definition, rawPoints, shapes, context, selected };
}

function handlePositions(item: RenderedDrawing, project: DrawingProjector): (ScreenPoint | null)[] {
  return item.context ? [...item.context.points] : item.rawPoints.map(project);
}

function svgViewport(svg: SVGSVGElement): Viewport {
  const bounds = svg.getBoundingClientRect();
  return { width: bounds.width || svg.clientWidth, height: bounds.height || svg.clientHeight };
}

/**
 * Moves every mounted drawing to the current projection without React, so
 * drawings stay on the chart while it pans. Returns false when a drawing's
 * shape structure changed and React must re-render it.
 */
function patchDrawings(svg: SVGSVGElement, frame: DrawingFrame, project: DrawingProjector): boolean {
  const viewport = svgViewport(svg);
  const byId = new Map(frame.drawings.map((drawing) => [drawing.drawingId, drawing]));
  let inSync = true;
  for (const group of svg.querySelectorAll<SVGGElement>('g[data-drawing-id]')) {
    const drawing = byId.get(group.dataset.drawingId ?? '');
    const item = drawing ? renderDrawing(drawing, frame, project, viewport) : null;
    if (!item) continue;
    if (shapeSignature(item.shapes) !== group.dataset.shapeSignature) {
      inSync = false;
      continue;
    }
    let handles: (ScreenPoint | null)[] | null = null;
    for (const child of group.children) {
      const element = child as SVGElement;
      const { shapeIndex, drawingPointIndex } = element.dataset;
      if (shapeIndex !== undefined) {
        patchShapeElement(element, item.shapes[Number(shapeIndex)]);
      } else if (drawingPointIndex !== undefined) {
        handles ??= handlePositions(item, project);
        const point = handles[Number(drawingPointIndex)];
        if (point) {
          element.setAttribute('cx', String(point.x));
          element.setAttribute('cy', String(point.y));
        }
      }
    }
  }
  return inSync;
}

function DraftPreview({ draft, definition, project, viewport, interval }: {
  draft: DrawingPoint[];
  definition: DrawingToolDefinition;
  project: DrawingProjector;
  viewport: Viewport;
  interval: string;
}) {
  if (definition.draftPreview === 'shapes') {
    const { shapes } = drawingGeometry({
      definition,
      project,
      rawPoints: draft,
      viewport,
      style: DEFAULT_DRAWING_STYLE,
      properties: drawingPropertiesWithDefaults(definition.id, undefined),
      text: definition.defaultText ?? '',
      interval,
      selected: false,
      locked: false,
      draft: true,
    });
    return <g data-drawing-draft="">{shapes.map((shape, index) => <ShapeElement key={index} shape={shape} index={index} />)}</g>;
  }
  const points = draft.map(project);
  if (points.length < 2 || points.some((point) => point === null)) return null;
  const [first, second] = points as ScreenPoint[];
  return points.length === 2
    ? <line x1={first.x} y1={first.y} x2={second.x} y2={second.y} className="draft" />
    : <polyline points={svgPoints(points as ScreenPoint[])} fill="none" className="draft" />;
}

function DrawingGroup({ item, project, onPressDrawing, onPressHandle }: {
  item: RenderedDrawing;
  project: DrawingProjector;
  onPressDrawing: (event: ReactPointerEvent<SVGElement>) => void;
  onPressHandle: (index: number) => (event: ReactPointerEvent<SVGElement>) => void;
}) {
  const { drawing, definition, shapes, selected } = item;
  const positions = selected && !drawing.locked ? handlePositions(item, project) : [];
  return (
    <g
      data-drawing-id={drawing.drawingId}
      data-locked={drawing.locked}
      data-selected={selected}
      data-shape-signature={shapeSignature(shapes)}
      onPointerDown={onPressDrawing}
    >
      {shapes.map((shape, index) => <ShapeElement key={index} shape={shape} index={index} />)}
      {positions.length > 0 ? handleIndices(definition, positions.length).map((index) => {
        const point = positions[index];
        return point ? (
          <circle
            key={`handle-${index}`}
            data-drawing-point-index={index}
            className={definition.handleClassName}
            cx={point.x}
            cy={point.y}
            r="6"
            onPointerDown={onPressHandle(index)}
          />
        ) : null;
      }) : null}
    </g>
  );
}

/** A chart placement at the pointer; over an indicator pane, its price is the indicator value. */
function chartPlacement(
  adapter: TradingChartAdapter | null,
  point: PointerPoint,
  clientY: number,
  source: ChartAlertPlacement['source'],
): { placement: ChartAlertPlacement; indicatorId: CoreIndicatorId | undefined } {
  const indicatorId = adapter?.indicatorPaneIdAtClientY(clientY) ?? undefined;
  const indicatorValue = indicatorId === undefined ? null : adapter?.indicatorValueFromClientY(indicatorId, clientY);
  return {
    placement: { ...point, ...(indicatorValue !== null && indicatorValue !== undefined ? { price: indicatorValue } : {}), source },
    indicatorId,
  };
}

/**
 * Keeps mounted drawings on the chart: viewport changes patch them in the same
 * callback; crosshair and pointer activity schedule a patch for the next frame.
 */
function useProjectionSync(
  adapter: TradingChartAdapter | null,
  svgRef: RefObject<SVGSVGElement | null>,
  refreshProjection: () => void,
  resized: (width: number, height: number) => void,
) {
  const resizedRef = useRef(resized);
  resizedRef.current = resized;
  useLayoutEffect(() => {
    if (!adapter) return;
    let frameRequest: number | null = null;
    let pointerActive = false;
    const invalidate = () => {
      if (frameRequest !== null) return;
      frameRequest = window.requestAnimationFrame(() => {
        frameRequest = null;
        refreshProjection();
      });
    };
    // Project directly into the already-mounted SVG during the chart viewport
    // callback. Waiting for React to reconcile a revision leaves the overlay one
    // or more frames behind Lightweight Charts while the user is dragging.
    const viewportChange = adapter.onViewportChange(refreshProjection);
    const crosshair = adapter.onCrosshair(() => invalidate());
    const stage = svgRef.current?.parentElement;
    const insideStage = (target: EventTarget | null) => target instanceof Node && Boolean(stage?.contains(target));
    const pointerDown = (event: PointerEvent) => {
      if (!insideStage(event.target)) return;
      pointerActive = true;
      invalidate();
    };
    const pointerMove = (event: PointerEvent) => {
      if (pointerActive && insideStage(event.target)) invalidate();
    };
    const pointerUp = () => {
      if (!pointerActive) return;
      pointerActive = false;
      invalidate();
    };
    window.addEventListener('pointerdown', pointerDown);
    window.addEventListener('pointermove', pointerMove);
    window.addEventListener('pointerup', pointerUp);
    const resize = new ResizeObserver((entries) => {
      const bounds = entries[0]?.contentRect;
      if (!bounds) return;
      resizedRef.current(bounds.width, bounds.height);
    });
    if (svgRef.current) resize.observe(svgRef.current);
    refreshProjection();
    return () => {
      viewportChange();
      crosshair();
      window.removeEventListener('pointerdown', pointerDown);
      window.removeEventListener('pointermove', pointerMove);
      window.removeEventListener('pointerup', pointerUp);
      if (frameRequest !== null) window.cancelAnimationFrame(frameRequest);
      resize.disconnect();
    };
  }, [adapter, refreshProjection, svgRef]);
}

export type TradingDrawingOverlayProps = {
  adapter: TradingChartAdapter | null;
  instrumentId: string;
  interval: string;
  tool: DrawingTool;
  snapMode: DrawingSnapMode;
  drawings: TradingDrawing[];
  selectedId: string | null;
  onAdd: (drawing: TradingDrawing) => void;
  onSelect: (id: string | null) => void;
  onMovePoint: (id: string, index: number, point: DrawingPoint) => void;
  onTranslateDrawing: (id: string, from: DrawingPoint, to: DrawingPoint) => void;
  onRemove: (id: string) => void;
  onToolComplete?: () => void;
  onAlertAtPoint?: (placement: ChartAlertPlacement, indicatorId?: CoreIndicatorId) => void;
  onContextMenu?: (placement: ChartAlertPlacement, indicatorId?: CoreIndicatorId) => void;
};

export function TradingDrawingOverlay({
  adapter,
  instrumentId,
  interval,
  tool,
  snapMode,
  drawings,
  selectedId,
  onAdd,
  onSelect,
  onMovePoint,
  onTranslateDrawing,
  onRemove,
  onToolComplete,
  onAlertAtPoint,
  onContextMenu: onChartContextMenu,
}: TradingDrawingOverlayProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0, revision: 0 });
  const drawingTool = isDrawingToolId(tool) ? tool : null;
  const definition = drawingTool ? drawingToolDefinition(drawingTool) : undefined;

  const pointFromClient = (clientX: number, clientY: number): PointerPoint | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const bounds = svg.getBoundingClientRect();
    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const point = adapter?.drawingPointFromCoordinate(x, y) ?? null;
    return point ? { ...snapDrawingPoint(point, snapMode), x, y } : null;
  };

  const editing = useDrawingEditing({
    tool, enabled: adapter !== null, pointFromClient, onSelect, onMovePoint, onTranslateDrawing, onRemove, onToolComplete,
  });
  const creation = useDrawingCreation(definition, (points) => {
    if (!definition || !drawingTool) return;
    onAdd({
      drawingId: crypto.randomUUID(),
      instrumentId,
      toolType: drawingTool,
      points,
      selected: true,
      revision: 1,
      style: DEFAULT_DRAWING_STYLE,
      locked: false,
      hidden: false,
      text: definition.defaultText ?? '',
      properties: drawingPropertiesWithDefaults(definition.id, undefined),
    });
    onToolComplete?.();
  });

  const frame: DrawingFrame = {
    drawings, selectedId, interval, handlePreview: editing.handlePreview, translationPreview: editing.translationPreview,
  };
  const frameRef = useRef(frame);
  frameRef.current = frame;

  const refreshProjection = useCallback(() => {
    const svg = svgRef.current;
    if (!svg || !adapter) return;
    if (!patchDrawings(svg, frameRef.current, (point) => adapter.projectDrawingPoint(point))) {
      setViewport((value) => ({ ...value, revision: value.revision + 1 }));
    }
  }, [adapter]);

  useProjectionSync(adapter, svgRef, refreshProjection, (width, height) => {
    setViewport((value) => ({ width, height, revision: value.revision + 1 }));
  });

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (tool === 'cursor') {
      if (event.target === event.currentTarget) onSelect(null);
      return;
    }
    const point = pointFromClient(event.clientX, event.clientY);
    if (!point) return;
    if (tool === 'alert') {
      const { placement, indicatorId } = chartPlacement(adapter, point, event.clientY, 'tool');
      onAlertAtPoint?.(placement, indicatorId);
      onToolComplete?.();
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    creation.pointerDown(point);
  };

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!creation.draft) return;
    const point = pointFromClient(event.clientX, event.clientY);
    if (point) creation.pointerMove(point);
  };

  const onContextMenu = (event: React.MouseEvent<SVGSVGElement>) => {
    const point = pointFromClient(event.clientX, event.clientY);
    event.preventDefault();
    event.stopPropagation();
    if (!point) return;
    const target = event.target instanceof Element ? event.target.closest<SVGGElement>('[data-drawing-id]') : null;
    const drawingId = target?.dataset.drawingId;
    const drawing = drawingId ? drawings.find((item) => item.drawingId === drawingId) : undefined;
    const { placement, indicatorId } = chartPlacement(adapter, point, event.clientY, 'context-menu');
    onChartContextMenu?.({
      ...placement,
      drawingId: drawing?.drawingId,
      drawingTool: drawing?.toolType,
      trendlinePoints: drawing ? drawingToolDefinition(drawing.toolType)?.lineAlertAnchors?.(drawing.points) : undefined,
    }, indicatorId);
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    if (!adapter) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    event.preventDefault();
    event.stopPropagation();
    adapter.zoomAtCoordinate(event.clientX - bounds.left, event.deltaY);
  };

  void viewport.revision;
  const project: DrawingProjector = (point) => adapter?.projectDrawingPoint(point) ?? null;
  // Measure like the imperative refresh does, so both always agree on shape structure.
  const size = svgRef.current ? svgViewport(svgRef.current) : { width: viewport.width, height: viewport.height };
  const rendered = drawings
    .filter((drawing) => !drawing.hidden)
    .map((drawing) => renderDrawing(drawing, frame, project, size))
    .filter((item): item is RenderedDrawing => item !== null);

  return (
    <svg
      ref={svgRef}
      className={`trading-drawing-overlay tool-${tool}`}
      aria-label="Interactive chart drawings and alert placement"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={creation.pointerUp}
      onDoubleClick={creation.doubleClick}
      onWheel={onWheel}
      onContextMenu={onContextMenu}
    >
      {rendered.map((item) => (
        <DrawingGroup
          key={item.drawing.drawingId}
          item={item}
          project={project}
          onPressDrawing={editing.dragDrawing(item.drawing)}
          onPressHandle={(index) => editing.dragHandle(item.drawing, index)}
        />
      ))}
      {creation.draft && definition ? (
        <DraftPreview draft={creation.draft} definition={definition} project={project} viewport={size} interval={interval} />
      ) : null}
    </svg>
  );
}
