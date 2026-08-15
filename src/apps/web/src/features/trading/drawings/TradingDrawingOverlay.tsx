import { useEffect, useRef, useState } from 'react';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import { tradingIntervalMinutes } from '../tradingIntervals';
import {
  DEFAULT_DRAWING_STYLE,
  snapDrawingPoint,
  type DrawingPoint,
  type DrawingSnapMode,
  type DrawingTool,
  type TradingDrawing,
} from './drawingCommands';
import './TradingDrawingMeasurement.css';

const twoPointTools = new Set<DrawingTool>([
  'trend-line',
  'ray',
  'arrow',
  'rectangle',
  'circle',
  'ellipse',
  'fibonacci',
  'measurement',
]);
const fibonacciLevels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

export type ChartAlertPlacement = DrawingPoint & {
  x: number;
  y: number;
  source: 'tool' | 'context-menu';
  drawingId?: string;
  drawingTool?: DrawingTool;
  trendlinePoints?: DrawingPoint[];
};

type HandlePreview = { drawingId: string; index: number; point: DrawingPoint };
type TranslationPreview = { drawingId: string; from: DrawingPoint; to: DrawingPoint };
type ProjectedPoint = { x: number; y: number };
type MeasurementVisual = {
  left: number;
  top: number;
  width: number;
  height: number;
  centerX: number;
  labelTop: number;
  labelWidth: number;
  label: string;
};

function measurementVisual(
  first: ProjectedPoint,
  second: ProjectedPoint,
  firstPoint: DrawingPoint,
  secondPoint: DrawingPoint,
  interval: string,
): MeasurementVisual {
  const left = Math.min(first.x, second.x);
  const top = Math.min(first.y, second.y);
  const width = Math.abs(second.x - first.x);
  const height = Math.abs(second.y - first.y);
  const centerX = left + width / 2;
  const delta = secondPoint.price - firstPoint.price;
  const percent = firstPoint.price === 0 ? 0 : delta / firstPoint.price * 100;
  const intervalMinutes = tradingIntervalMinutes(interval) ?? 1;
  const durationMinutes = Math.abs(Date.parse(secondPoint.time) - Date.parse(firstPoint.time)) / 60_000;
  const bars = Number.isFinite(durationMinutes) ? Math.max(1, Math.round(durationMinutes / intervalMinutes)) : 1;
  const formatValue = (value: number) => Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
  const label = `${delta < 0 ? '-' : ''}${formatValue(delta)} (${percent < 0 ? '-' : ''}${Math.abs(percent).toFixed(2)}%) ${bars.toLocaleString()}`;
  const labelWidth = Math.max(126, label.length * 7.2 + 18);
  return {
    left,
    top,
    width,
    height,
    centerX,
    labelTop: Math.max(5, top - 40),
    labelWidth,
    label,
  };
}

function translatedPoints(points: DrawingPoint[], preview: TranslationPreview | null, drawingId: string): DrawingPoint[] {
  if (!preview || preview.drawingId !== drawingId) return points;
  const fromTime = Date.parse(preview.from.time);
  const toTime = Date.parse(preview.to.time);
  const timeDelta = toTime - fromTime;
  const priceDelta = preview.to.price - preview.from.price;
  return points.map((point) => ({
    time: new Date(Date.parse(point.time) + timeDelta).toISOString(),
    price: point.price + priceDelta,
  }));
}

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
}: {
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
  onAlertAtPoint?: (placement: ChartAlertPlacement) => void;
  onContextMenu?: (placement: ChartAlertPlacement) => void;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [draftStart, setDraftStart] = useState<DrawingPoint | null>(null);
  const [draftEnd, setDraftEnd] = useState<DrawingPoint | null>(null);
  const [handlePreview, setHandlePreview] = useState<HandlePreview | null>(null);
  const [translationPreview, setTranslationPreview] = useState<TranslationPreview | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0, revision: 0 });

  useEffect(() => {
    if (!adapter) return;
    const visibleRange = adapter.onVisibleRange(() => {
      setViewport((value) => ({ ...value, revision: value.revision + 1 }));
    });
    const resize = new ResizeObserver((entries) => {
      const bounds = entries[0]?.contentRect;
      if (!bounds) return;
      setViewport((value) => ({
        width: bounds.width,
        height: bounds.height,
        revision: value.revision + 1,
      }));
    });
    if (svgRef.current) resize.observe(svgRef.current);
    return () => {
      visibleRange();
      resize.disconnect();
    };
  }, [adapter]);

  const pointFromClient = (clientX: number, clientY: number): (DrawingPoint & { x: number; y: number }) | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const bounds = svg.getBoundingClientRect();
    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const point = adapter?.drawingPointFromCoordinate(x, y) ?? null;
    return point ? { ...snapDrawingPoint(point, snapMode), x, y } : null;
  };

  const pointFromEvent = (event: React.PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>): (DrawingPoint & { x: number; y: number }) | null => (
    pointFromClient(event.clientX, event.clientY)
  );

  const createDrawing = (points: DrawingPoint[]) => {
    if (tool === 'cursor' || tool === 'alert' || tool === 'eraser') return;
    onAdd({
      drawingId: crypto.randomUUID(),
      instrumentId,
      toolType: tool,
      points,
      selected: true,
      revision: 1,
      style: DEFAULT_DRAWING_STYLE,
      locked: false,
      hidden: false,
      text: tool === 'text' ? 'Market note' : '',
    });
    onToolComplete?.();
  };

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (tool === 'cursor') {
      if (event.target === event.currentTarget) onSelect(null);
      return;
    }
    const point = pointFromEvent(event);
    if (!point) return;
    if (tool === 'alert') {
      onAlertAtPoint?.({ ...point, source: 'tool' });
      onToolComplete?.();
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    if (!twoPointTools.has(tool)) {
      createDrawing([point]);
      return;
    }
    setDraftStart(point);
    setDraftEnd(point);
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!draftStart || !twoPointTools.has(tool)) return;
    const point = pointFromEvent(event);
    if (point) setDraftEnd(point);
  };

  const onPointerUp = () => {
    if (draftStart && draftEnd && twoPointTools.has(tool)) createDrawing([draftStart, draftEnd]);
    setDraftStart(null);
    setDraftEnd(null);
  };

  const onContextMenu = (event: React.MouseEvent<SVGSVGElement>) => {
    const point = pointFromEvent(event);
    event.preventDefault();
    event.stopPropagation();
    if (!point) return;
    const target = event.target instanceof Element
      ? event.target.closest<SVGGElement>('[data-drawing-id]')
      : null;
    const drawingId = target?.dataset.drawingId;
    const drawing = drawingId ? drawings.find((item) => item.drawingId === drawingId) : undefined;
    onChartContextMenu?.({
      ...point,
      source: 'context-menu',
      drawingId: drawing?.drawingId,
      drawingTool: drawing?.toolType,
      trendlinePoints: drawing?.toolType === 'trend-line' ? drawing.points.slice(0, 2) : undefined,
    });
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    if (!adapter) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    event.preventDefault();
    event.stopPropagation();
    adapter.zoomAtCoordinate(event.clientX - bounds.left, event.deltaY);
  };

  const dragHandle = (drawing: TradingDrawing, index: number) => (event: React.PointerEvent<SVGCircleElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (drawing.locked || !adapter) return;
    const move = (pointer: PointerEvent) => {
      const point = pointFromClient(pointer.clientX, pointer.clientY);
      if (point) setHandlePreview({ drawingId: drawing.drawingId, index, point });
    };
    const up = (pointer: PointerEvent) => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      const point = pointFromClient(pointer.clientX, pointer.clientY);
      setHandlePreview(null);
      if (point) onMovePoint(drawing.drawingId, index, point);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const dragDrawing = (drawing: TradingDrawing) => (event: React.PointerEvent<SVGGElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (tool === 'eraser') {
      onRemove(drawing.drawingId);
      onToolComplete?.();
      return;
    }
    onSelect(drawing.drawingId);
    if (tool !== 'cursor' || drawing.locked || !adapter) return;
    const start = pointFromClient(event.clientX, event.clientY);
    if (!start) return;
    const move = (pointer: PointerEvent) => {
      const point = pointFromClient(pointer.clientX, pointer.clientY);
      if (point) setTranslationPreview({ drawingId: drawing.drawingId, from: start, to: point });
    };
    const up = (pointer: PointerEvent) => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      const point = pointFromClient(pointer.clientX, pointer.clientY);
      setTranslationPreview(null);
      if (point && (point.time !== start.time || point.price !== start.price)) {
        onTranslateDrawing(drawing.drawingId, start, point);
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const projected = drawings
    .filter((drawing) => !drawing.hidden)
    .map((drawing) => {
      let points = translatedPoints(drawing.points, translationPreview, drawing.drawingId);
      if (handlePreview?.drawingId === drawing.drawingId) {
        points = points.map((point, index) => index === handlePreview.index ? handlePreview.point : point);
      }
      return {
        drawing,
        rawPoints: points,
        points: points.map((point) => adapter?.projectDrawingPoint(point) ?? null),
      };
    });
  void viewport.revision;

  const draftCoordinates = draftStart && draftEnd
    ? [adapter?.projectDrawingPoint(draftStart), adapter?.projectDrawingPoint(draftEnd)]
    : null;
  const draftFirst = draftCoordinates?.[0] ?? null;
  const draftSecond = draftCoordinates?.[1] ?? null;

  const renderMeasurement = (
    visual: MeasurementVisual,
    color: string,
    first: ProjectedPoint,
    second: ProjectedPoint,
    drawing?: TradingDrawing,
  ) => {
    const selected = drawing?.drawingId === selectedId;
    const editable = selected && !drawing?.locked;
    return (
      <g className="trading-measurement" data-selected={selected}>
        <rect
          className="trading-measurement-area"
          x={visual.left}
          y={visual.top}
          width={visual.width}
          height={visual.height}
          fill={color}
          fillOpacity=".14"
        />
        <line className="trading-measurement-edge" stroke={color} x1={visual.left} x2={visual.left + visual.width} y1={visual.top} y2={visual.top} />
        <line className="trading-measurement-edge" stroke={color} x1={visual.left} x2={visual.left + visual.width} y1={visual.top + visual.height} y2={visual.top + visual.height} />
        <line className="trading-measurement-axis" stroke={color} x1={visual.centerX} x2={visual.centerX} y1={visual.top} y2={visual.top + visual.height} />
        <path className="trading-measurement-arrow" stroke={color} d={`M ${visual.centerX - 7} ${visual.top + 8} L ${visual.centerX} ${visual.top} L ${visual.centerX + 7} ${visual.top + 8}`} />
        <g className="trading-measurement-label">
          <rect x={visual.centerX - visual.labelWidth / 2} y={visual.labelTop} width={visual.labelWidth} height="30" rx="5" />
          <text x={visual.centerX} y={visual.labelTop + 19} textAnchor="middle">{visual.label}</text>
        </g>
        {editable ? (
          <>
            <circle className="trading-measurement-handle" cx={first.x} cy={first.y} r="6" onPointerDown={drawing ? dragHandle(drawing, 0) : undefined} />
            <circle className="trading-measurement-handle" cx={second.x} cy={second.y} r="6" onPointerDown={drawing ? dragHandle(drawing, 1) : undefined} />
          </>
        ) : null}
      </g>
    );
  };

  return (
    <svg
      ref={svgRef}
      className={`trading-drawing-overlay tool-${tool}`}
      aria-label="Interactive chart drawings and alert placement"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
      onContextMenu={onContextMenu}
    >
      {projected.map(({ drawing, rawPoints, points }) => {
        const first = points[0];
        const second = points[1];
        const rawFirst = rawPoints[0];
        const rawSecond = rawPoints[1];
        if (!first) return null;
        const selected = drawing.drawingId === selectedId;
        const style = drawing.style ?? DEFAULT_DRAWING_STYLE;
        const lineProps = {
          className: selected ? 'selected' : undefined,
          stroke: style.color,
          strokeWidth: style.lineWidth,
          strokeDasharray: style.lineStyle === 'dashed' ? '6 4' : undefined,
        };
        const arrowMarkerId = `trading-drawing-arrow-${drawing.drawingId}`;
        const measurement = drawing.toolType === 'measurement' && second && rawFirst && rawSecond
          ? measurementVisual(first, second, rawFirst, rawSecond, interval)
          : null;
        const measurementColor = drawing.toolType === 'measurement' && style.color === DEFAULT_DRAWING_STYLE.color ? '#2962ff' : style.color;
        const ray = (() => {
          if (drawing.toolType !== 'ray' || !second) return null;
          const dx = second.x - first.x;
          const targetX = dx >= 0 ? viewport.width : 0;
          if (Math.abs(dx) < 0.0001) {
            return { x: first.x, y: second.y >= first.y ? viewport.height : 0 };
          }
          const slope = (second.y - first.y) / dx;
          return { x: targetX, y: first.y + slope * (targetX - first.x) };
        })();
        return (
          <g
            key={drawing.drawingId}
            data-drawing-id={drawing.drawingId}
            data-locked={drawing.locked}
            data-selected={selected}
            onPointerDown={dragDrawing(drawing)}
          >
            {drawing.toolType === 'arrow' ? (
              <defs>
                <marker id={arrowMarkerId} markerHeight="6" markerWidth="6" orient="auto" refX="5" refY="3" markerUnits="strokeWidth">
                  <path d="M 0 0 L 6 3 L 0 6 z" fill={style.color} />
                </marker>
              </defs>
            ) : null}
            {drawing.toolType === 'dot' ? <circle className={`drawing-dot${selected ? ' selected' : ''}`} cx={first.x} cy={first.y} r={selected ? 5 : 4} fill={style.color} stroke={selected ? '#ffd43b' : style.color} strokeWidth={style.lineWidth} /> : null}
            {drawing.toolType === 'horizontal-line' ? <line {...lineProps} x1="0" x2="100%" y1={first.y} y2={first.y} /> : null}
            {drawing.toolType === 'horizontal-ray' ? <line {...lineProps} x1={first.x} x2="100%" y1={first.y} y2={first.y} /> : null}
            {drawing.toolType === 'vertical-line' ? <line {...lineProps} x1={first.x} x2={first.x} y1="0" y2="100%" /> : null}
            {drawing.toolType === 'crossline' ? <><line {...lineProps} x1="0" x2="100%" y1={first.y} y2={first.y} /><line {...lineProps} x1={first.x} x2={first.x} y1="0" y2="100%" /></> : null}
            {drawing.toolType === 'trend-line' || drawing.toolType === 'arrow' ? (
              second ? <line {...lineProps} markerEnd={drawing.toolType === 'arrow' ? `url(#${arrowMarkerId})` : undefined} x1={first.x} y1={first.y} x2={second.x} y2={second.y} /> : null
            ) : null}
            {measurement ? renderMeasurement(measurement, measurementColor, first, second!, drawing) : null}
            {ray ? <line {...lineProps} x1={first.x} y1={first.y} x2={ray.x} y2={ray.y} /> : null}
            {drawing.toolType === 'rectangle' && second ? <rect {...lineProps} x={Math.min(first.x, second.x)} y={Math.min(first.y, second.y)} width={Math.abs(second.x - first.x)} height={Math.abs(second.y - first.y)} fill={`${style.color}20`} /> : null}
            {drawing.toolType === 'circle' && second ? <ellipse {...lineProps} cx={(first.x + second.x) / 2} cy={(first.y + second.y) / 2} rx={Math.max(Math.abs(second.x - first.x), Math.abs(second.y - first.y)) / 2} ry={Math.max(Math.abs(second.x - first.x), Math.abs(second.y - first.y)) / 2} fill={`${style.color}20`} /> : null}
            {drawing.toolType === 'ellipse' && second ? <ellipse {...lineProps} cx={(first.x + second.x) / 2} cy={(first.y + second.y) / 2} rx={Math.abs(second.x - first.x) / 2} ry={Math.abs(second.y - first.y) / 2} fill={`${style.color}20`} /> : null}
            {drawing.toolType === 'fibonacci' && second ? fibonacciLevels.map((level) => {
              const y = first.y + (second.y - first.y) * level;
              return <g key={level}><line {...lineProps} x1={Math.min(first.x, second.x)} x2={Math.max(first.x, second.x)} y1={y} y2={y} /><text x={Math.max(first.x, second.x) + 4} y={y - 2}>{level}</text></g>;
            }) : null}
            {drawing.toolType === 'text' ? <text className={selected ? 'selected' : undefined} x={first.x} y={first.y} fill={style.color}>{drawing.text || 'Market note'}</text> : null}
            {drawing.toolType === 'arrow' && second ? <circle className="drawing-hit-target" cx={second.x} cy={second.y} r="11" /> : null}
            {selected && !drawing.locked && drawing.toolType !== 'measurement' ? points.map((point, index) => point ? <circle key={index} cx={point.x} cy={point.y} r="6" onPointerDown={dragHandle(drawing, index)} /> : null) : null}
          </g>
        );
      })}
      {draftFirst && draftSecond && draftStart && draftEnd && tool === 'measurement' ? (
        renderMeasurement(
          measurementVisual(draftFirst, draftSecond, draftStart, draftEnd, interval),
          '#2962ff',
          draftFirst,
          draftSecond,
        )
      ) : draftFirst && draftSecond ? (
        <line x1={draftFirst.x} y1={draftFirst.y} x2={draftSecond.x} y2={draftSecond.y} className="draft" />
      ) : null}
    </svg>
  );
}
