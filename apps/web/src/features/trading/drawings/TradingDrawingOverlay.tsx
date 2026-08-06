import { useEffect, useRef, useState } from 'react';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import {
  DEFAULT_DRAWING_STYLE,
  snapDrawingPoint,
  type DrawingPoint,
  type DrawingSnapMode,
  type DrawingTool,
  type TradingDrawing,
} from './drawingCommands';

const twoPointTools = new Set<DrawingTool>(['trend-line', 'ray', 'rectangle', 'fibonacci', 'measurement']);
const fibonacciLevels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

export type ChartAlertPlacement = DrawingPoint & { x: number; y: number; source: 'tool' | 'context-menu' };

type HandlePreview = { drawingId: string; index: number; point: DrawingPoint };
type TranslationPreview = { drawingId: string; from: DrawingPoint; to: DrawingPoint };

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
  tool,
  snapMode,
  drawings,
  selectedId,
  onAdd,
  onSelect,
  onMovePoint,
  onTranslateDrawing,
  onAlertAtPoint,
}: {
  adapter: TradingChartAdapter | null;
  instrumentId: string;
  tool: DrawingTool;
  snapMode: DrawingSnapMode;
  drawings: TradingDrawing[];
  selectedId: string | null;
  onAdd: (drawing: TradingDrawing) => void;
  onSelect: (id: string | null) => void;
  onMovePoint: (id: string, index: number, point: DrawingPoint) => void;
  onTranslateDrawing: (id: string, from: DrawingPoint, to: DrawingPoint) => void;
  onAlertAtPoint?: (placement: ChartAlertPlacement) => void;
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
    if (tool === 'cursor' || tool === 'alert') return;
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
    if (!point || !onAlertAtPoint) return;
    event.preventDefault();
    onAlertAtPoint({ ...point, source: 'context-menu' });
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
        points: points.map((point) => adapter?.projectDrawingPoint(point) ?? null),
      };
    });
  void viewport.revision;

  const draftCoordinates = draftStart && draftEnd
    ? [adapter?.projectDrawingPoint(draftStart), adapter?.projectDrawingPoint(draftEnd)]
    : null;

  return (
    <svg
      ref={svgRef}
      className={`trading-drawing-overlay tool-${tool}`}
      aria-label="Interactive chart drawings and alert placement"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onContextMenu={onContextMenu}
    >
      {projected.map(({ drawing, points }) => {
        const first = points[0];
        const second = points[1];
        if (!first) return null;
        const selected = drawing.drawingId === selectedId;
        const style = drawing.style ?? DEFAULT_DRAWING_STYLE;
        const lineProps = {
          className: selected ? 'selected' : undefined,
          stroke: style.color,
          strokeWidth: style.lineWidth,
          strokeDasharray: style.lineStyle === 'dashed' ? '6 4' : undefined,
        };
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
            data-locked={drawing.locked}
            data-selected={selected}
            onPointerDown={dragDrawing(drawing)}
          >
            {drawing.toolType === 'horizontal-line' ? <line {...lineProps} x1="0" x2="100%" y1={first.y} y2={first.y} /> : null}
            {drawing.toolType === 'vertical-line' ? <line {...lineProps} x1={first.x} x2={first.x} y1="0" y2="100%" /> : null}
            {(drawing.toolType === 'trend-line' || drawing.toolType === 'measurement') && second ? <line {...lineProps} x1={first.x} y1={first.y} x2={second.x} y2={second.y} /> : null}
            {ray ? <line {...lineProps} x1={first.x} y1={first.y} x2={ray.x} y2={ray.y} /> : null}
            {drawing.toolType === 'rectangle' && second ? <rect {...lineProps} x={Math.min(first.x, second.x)} y={Math.min(first.y, second.y)} width={Math.abs(second.x - first.x)} height={Math.abs(second.y - first.y)} fill={`${style.color}20`} /> : null}
            {drawing.toolType === 'fibonacci' && second ? fibonacciLevels.map((level) => {
              const y = first.y + (second.y - first.y) * level;
              return <g key={level}><line {...lineProps} x1={Math.min(first.x, second.x)} x2={Math.max(first.x, second.x)} y1={y} y2={y} /><text x={Math.max(first.x, second.x) + 4} y={y - 2}>{level}</text></g>;
            }) : null}
            {drawing.toolType === 'text' ? <text className={selected ? 'selected' : undefined} x={first.x} y={first.y} fill={style.color}>{drawing.text || 'Market note'}</text> : null}
            {drawing.toolType === 'measurement' && second ? <text x={(first.x + second.x) / 2} y={(first.y + second.y) / 2 - 6}>{`${(drawing.points[1].price - drawing.points[0].price).toFixed(2)}`}</text> : null}
            {selected && !drawing.locked ? points.map((point, index) => point ? <circle key={index} cx={point.x} cy={point.y} r="6" onPointerDown={dragHandle(drawing, index)} /> : null) : null}
          </g>
        );
      })}
      {draftCoordinates?.[0] && draftCoordinates[1] ? <line x1={draftCoordinates[0].x} y1={draftCoordinates[0].y} x2={draftCoordinates[1].x} y2={draftCoordinates[1].y} className="draft" /> : null}
    </svg>
  );
}
