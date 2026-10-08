import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import type { CoreIndicatorId } from '../indicators/coreIndicators';
import type { TradingAlertIndicatorId } from '../tradingTypes';
import {
  DEFAULT_DRAWING_STYLE,
  type DrawingPoint,
  type DrawingSnapMode,
  type DrawingTool,
  type TradingDrawing,
} from './drawingCommands';
import {
  canvasScene,
  chartAccessFor,
  draftShapes,
  handlePositions,
  patchDraft,
  patchDrawings,
  renderDrawing,
  svgViewport,
  type DrawingFrame,
  type RenderedDrawing,
} from './drawingFrame';
import { storedDrawingRendererMode, type DrawingRendererMode } from './drawingRenderer';
import { ShapeElement } from './svgShapes';
import { drawingPropertiesWithDefaults, drawingToolDefinition, isDrawingToolId } from './tools/registry';
import { type DrawingProjector } from './tools/scene';
import { shapeSignature } from './tools/shapes';
import {
  handleIndices,
  type DrawingAlertLevel,
  type DrawingContextAction,
  type DrawingShape,
  type DrawingToolDefinition,
} from './tools/types';
import { useCanvasDrawingHost } from './useCanvasDrawingHost';
import { useDrawingCreation, type PointerPoint } from './useDrawingCreation';
import { useDrawingEditing } from './useDrawingEditing';
import { creationPointLocator, drawingPointLocator, locatePoint } from './drawingPointer';
import { useProjectionSync } from './useProjectionSync';
import './TradingDrawingMeasurement.css';

export type ChartAlertPlacement = DrawingPoint & {
  x: number;
  y: number;
  source: 'tool' | 'context-menu';
  indicatorId?: TradingAlertIndicatorId;
  indicatorPeriod?: number;
  drawingId?: string;
  drawingTool?: DrawingTool;
  /** Anchors of the drawing's first two-anchor alert level, for the chart's line alert. */
  trendlinePoints?: DrawingPoint[];
  /** All alert levels the drawing's tool defines (TVP-1.4). */
  drawingAlertLevels?: DrawingAlertLevel[];
  /** Context-menu actions the drawing's tool offers. */
  drawingActions?: readonly DrawingContextAction[];
};


function newDrawing(toolType: TradingDrawing['toolType'], definition: DrawingToolDefinition, instrumentId: string, points: DrawingPoint[]): TradingDrawing {
  return {
    drawingId: crypto.randomUUID(),
    instrumentId,
    toolType,
    points,
    selected: true,
    revision: 1,
    style: DEFAULT_DRAWING_STYLE,
    locked: false,
    hidden: false,
    text: definition.defaultText ?? '',
    properties: drawingPropertiesWithDefaults(definition.id, undefined),
  };
}

function ShapeGroup({ shapes, signature }: { shapes: readonly DrawingShape[]; signature: boolean }) {
  return (
    <g data-drawing-draft="" data-shape-signature={signature ? shapeSignature(shapes) : undefined}>
      {shapes.map((shape, index) => <ShapeElement key={index} shape={shape} index={index} />)}
    </g>
  );
}

function DrawingGroup({ item, project, viewport, withShapes, onPressDrawing, onPressHandle }: {
  item: RenderedDrawing;
  project: DrawingProjector;
  viewport: { width: number; height: number };
  withShapes: boolean;
  onPressDrawing: (event: ReactPointerEvent<SVGElement>) => void;
  onPressHandle: (index: number) => (event: ReactPointerEvent<SVGElement>) => void;
}) {
  const { drawing, definition, shapes, selected } = item;
  const positions = selected && !drawing.locked ? handlePositions(item, project, viewport) : [];
  return (
    <g
      data-drawing-id={drawing.drawingId}
      data-locked={drawing.locked}
      data-selected={selected}
      data-shape-signature={withShapes ? shapeSignature(shapes) : undefined}
      onPointerDown={onPressDrawing}
    >
      {withShapes ? shapes.map((shape, index) => <ShapeElement key={index} shape={shape} index={index} />) : null}
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
    placement: { x: point.x, y: point.y, time: point.time, price: indicatorValue ?? point.price, source },
    indicatorId,
  };
}

/** What a drawing's tool offers from the context menu: its alert levels and actions. */
function drawingMenuEntries(drawing: TradingDrawing | undefined): Partial<ChartAlertPlacement> {
  if (!drawing) return {};
  const definition = drawingToolDefinition(drawing.toolType);
  const levels = definition?.alertLevels?.(drawing.points, drawingPropertiesWithDefaults(drawing.toolType, drawing.properties)) ?? [];
  const line = levels.find((level) => level.anchors.length === 2);
  return {
    drawingId: drawing.drawingId,
    drawingTool: drawing.toolType,
    trendlinePoints: line?.anchors.map((point) => ({ time: point.time, price: point.price })),
    drawingAlertLevels: levels.length > 0 ? levels : undefined,
    drawingActions: definition?.contextActions,
  };
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
  /** Overrides the stored renderer switch (`drawingRenderer.ts`). */
  renderer?: DrawingRendererMode;
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
  renderer,
}: TradingDrawingOverlayProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [storedRenderer] = useState(storedDrawingRendererMode);
  const canvas = (renderer ?? storedRenderer) === 'canvas';
  const [viewport, setViewport] = useState({ width: 0, height: 0, revision: 0 });
  const rerender = useCallback(() => setViewport((value) => ({ ...value, revision: value.revision + 1 })), []);
  const drawingTool = isDrawingToolId(tool) ? tool : null;
  const definition = drawingTool ? drawingToolDefinition(drawingTool) : undefined;
  const plainPoint = (clientX: number, clientY: number) => locatePoint(svgRef.current, adapter, clientX, clientY, { snapMode, snap: true, screen: false });
  const pointFor = drawingPointLocator(svgRef, adapter, snapMode);


  const editing = useDrawingEditing({
    tool, enabled: adapter !== null, pointFor, onSelect, onMovePoint, onTranslateDrawing, onRemove, onToolComplete,
  });
  const frameRef = useRef<DrawingFrame | null>(null);
  const creation = useDrawingCreation(definition, (points) => {
    if (!definition || !drawingTool) return;
    onAdd(newDrawing(drawingTool, definition, instrumentId, points));
    onToolComplete?.();
  }, () => {
    const svg = svgRef.current;
    if (svg && frameRef.current && !patchDraft(svg, frameRef.current, chartAccessFor(adapter))) rerender();
  });
  const creationPoint = creationPointLocator(svgRef, adapter, snapMode, definition, () => (creation.draftRef.current ?? []).slice(0, -1));

  const frame: DrawingFrame = {
    drawings,
    selectedId,
    interval,
    handlePreview: editing.handlePreview,
    translationPreview: editing.translationPreview,
    draft: creation.draftRef.current && definition ? { definition, points: creation.draftRef.current } : null,
  };
  frameRef.current = frame;
  const drawingsRef = useRef(drawings);
  drawingsRef.current = drawings;
  const canvasHost = useCanvasDrawingHost({
    enabled: canvas,
    adapter,
    svgRef,
    drawingsRef,
    scene: (size) => canvasScene(frameRef.current ?? frame, adapter, size),
  });

  const refreshProjection = useCallback(() => {
    const svg = svgRef.current;
    if (svg && adapter && frameRef.current && !patchDrawings(svg, frameRef.current, chartAccessFor(adapter), !canvas)) rerender();
  }, [adapter, canvas, rerender]);

  useProjectionSync(adapter, svgRef, refreshProjection, (width, height) => {
    setViewport((value) => ({ width, height, revision: value.revision + 1 }));
  });

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    // Canvas renderer: presses on painted drawings edit them (SVG drawings handle their own).
    const painted = canvas && editing.edits ? canvasHost.drawingAt(event.clientX, event.clientY) : null;
    if (painted) {
      editing.dragDrawing(painted)(event);
      return;
    }
    if (tool === 'cursor') {
      if (event.target === event.currentTarget) onSelect(null);
      return;
    }
    if (tool === 'alert') {
      const point = plainPoint(event.clientX, event.clientY);
      if (!point) return;
      const { placement, indicatorId } = chartPlacement(adapter, point, event.clientY, 'tool');
      onAlertAtPoint?.(placement, indicatorId);
      onToolComplete?.();
      return;
    }
    const point = creationPoint(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    creation.pointerDown(point);
  };

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!creation.draftRef.current) return;
    const point = creationPoint(event);
    if (point) creation.pointerMove(point);
  };

  const onContextMenu = (event: React.MouseEvent<SVGSVGElement>) => {
    const point = plainPoint(event.clientX, event.clientY);
    event.preventDefault();
    event.stopPropagation();
    if (!point) return;
    const target = event.target instanceof Element ? event.target.closest<SVGElement>('[data-drawing-id]') : null;
    const drawingId = target?.dataset.drawingId ?? (canvas ? canvasHost.drawingAt(event.clientX, event.clientY)?.drawingId : undefined);
    const drawing = drawingId ? drawings.find((item) => item.drawingId === drawingId) : undefined;
    const { placement, indicatorId } = chartPlacement(adapter, point, event.clientY, 'context-menu');
    onChartContextMenu?.({ ...placement, ...drawingMenuEntries(drawing) }, indicatorId);
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    if (!adapter) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    event.preventDefault();
    event.stopPropagation();
    adapter.zoomAtCoordinate(event.clientX - bounds.left, event.deltaY);
  };

  void viewport.revision;
  const access = chartAccessFor(adapter);
  // Measure like the imperative refresh does, so both always agree on shape structure.
  const size = svgRef.current ? svgViewport(svgRef.current) : { width: viewport.width, height: viewport.height };
  const rendered = drawings
    .filter((drawing) => !drawing.hidden && (!canvas || drawing.drawingId === selectedId))
    .map((drawing) => renderDrawing(drawing, frame, access, size))
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
          project={access.project}
          viewport={size}
          withShapes={!canvas}
          onPressDrawing={editing.dragDrawing(item.drawing)}
          onPressHandle={(index) => editing.dragHandle(item.drawing, index)}
        />
      ))}
      {frame.draft ? <ShapeGroup shapes={draftShapes(frame.draft, access, size, interval)} signature /> : null}
    </svg>
  );
}
