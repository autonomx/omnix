import { useMemo, useRef, useState } from 'react';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import type { DrawingPoint, DrawingTool, TradingDrawing } from './drawingCommands';

export function TradingDrawingOverlay({
  adapter,
  instrumentId,
  tool,
  drawings,
  selectedId,
  onAdd,
  onSelect,
  onMovePoint,
}: {
  adapter: TradingChartAdapter | null;
  instrumentId: string;
  tool: DrawingTool;
  drawings: TradingDrawing[];
  selectedId: string | null;
  onAdd: (drawing: TradingDrawing) => void;
  onSelect: (id: string | null) => void;
  onMovePoint: (id: string, index: number, point: DrawingPoint) => void;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [draftStart, setDraftStart] = useState<DrawingPoint | null>(null);
  const [draftEnd, setDraftEnd] = useState<DrawingPoint | null>(null);
  const projected = useMemo(() => drawings.map((drawing) => ({
    drawing,
    points: drawing.points.map((point) => adapter?.projectDrawingPoint(point) ?? null),
  })), [adapter, drawings]);

  const pointFromEvent = (event: React.PointerEvent<SVGSVGElement>): DrawingPoint | null => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return adapter?.drawingPointFromCoordinate(event.clientX - bounds.left, event.clientY - bounds.top) ?? null;
  };

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (tool === 'cursor') {
      if (event.target === event.currentTarget) onSelect(null);
      return;
    }
    const point = pointFromEvent(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === 'horizontal-line') {
      onAdd({ drawingId: crypto.randomUUID(), instrumentId, toolType: tool, points: [point], selected: true, revision: 1 });
      return;
    }
    setDraftStart(point);
    setDraftEnd(point);
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!draftStart || tool !== 'trend-line') return;
    const point = pointFromEvent(event);
    if (point) setDraftEnd(point);
  };

  const onPointerUp = () => {
    if (draftStart && draftEnd && tool === 'trend-line') {
      onAdd({ drawingId: crypto.randomUUID(), instrumentId, toolType: tool, points: [draftStart, draftEnd], selected: true, revision: 1 });
    }
    setDraftStart(null);
    setDraftEnd(null);
  };

  const dragHandle = (drawing: TradingDrawing, index: number) => (event: React.PointerEvent<SVGCircleElement>) => {
    event.stopPropagation();
    const svg = svgRef.current;
    if (!svg || !adapter) return;
    svg.setPointerCapture(event.pointerId);
    const bounds = svg.getBoundingClientRect();
    const move = (pointer: PointerEvent) => {
      const point = adapter.drawingPointFromCoordinate(pointer.clientX - bounds.left, pointer.clientY - bounds.top);
      if (point) onMovePoint(drawing.drawingId, index, point);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const draftCoordinates = draftStart && draftEnd ? [adapter?.projectDrawingPoint(draftStart), adapter?.projectDrawingPoint(draftEnd)] : null;
  return (
    <svg
      ref={svgRef}
      className={`trading-drawing-overlay tool-${tool}`}
      aria-label="Interactive chart drawings"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      {projected.map(({ drawing, points }) => {
        const first = points[0];
        const second = points[1];
        if (!first) return null;
        const selected = drawing.drawingId === selectedId;
        return (
          <g key={drawing.drawingId} onPointerDown={(event) => { event.stopPropagation(); onSelect(drawing.drawingId); }}>
            {drawing.toolType === 'horizontal-line' ? <line x1="0" x2="100%" y1={first.y} y2={first.y} className={selected ? 'selected' : ''} /> : second ? <line x1={first.x} y1={first.y} x2={second.x} y2={second.y} className={selected ? 'selected' : ''} /> : null}
            {selected ? points.map((point, index) => point ? <circle key={index} cx={point.x} cy={point.y} r="6" onPointerDown={dragHandle(drawing, index)} /> : null) : null}
          </g>
        );
      })}
      {draftCoordinates?.[0] && draftCoordinates[1] ? <line x1={draftCoordinates[0].x} y1={draftCoordinates[0].y} x2={draftCoordinates[1].x} y2={draftCoordinates[1].y} className="draft" /> : null}
    </svg>
  );
}
