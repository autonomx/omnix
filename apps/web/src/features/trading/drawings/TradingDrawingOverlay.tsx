import { useMemo, useRef, useState } from 'react';
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
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [draftStart, setDraftStart] = useState<DrawingPoint | null>(null);
  const [draftEnd, setDraftEnd] = useState<DrawingPoint | null>(null);
  const projected = useMemo(() => drawings.filter((drawing) => !drawing.hidden).map((drawing) => ({
    drawing,
    points: drawing.points.map((point) => adapter?.projectDrawingPoint(point) ?? null),
  })), [adapter, drawings]);

  const pointFromEvent = (event: React.PointerEvent<SVGSVGElement>): DrawingPoint | null => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const point = adapter?.drawingPointFromCoordinate(event.clientX - bounds.left, event.clientY - bounds.top) ?? null;
    return point ? snapDrawingPoint(point, snapMode) : null;
  };

  const createDrawing = (points: DrawingPoint[]) => {
    if (tool === 'cursor') return;
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

  const dragHandle = (drawing: TradingDrawing, index: number) => (event: React.PointerEvent<SVGCircleElement>) => {
    event.stopPropagation();
    if (drawing.locked) return;
    const svg = svgRef.current;
    if (!svg || !adapter) return;
    svg.setPointerCapture(event.pointerId);
    const bounds = svg.getBoundingClientRect();
    const move = (pointer: PointerEvent) => {
      const point = adapter.drawingPointFromCoordinate(pointer.clientX - bounds.left, pointer.clientY - bounds.top);
      if (point) onMovePoint(drawing.drawingId, index, snapDrawingPoint(point, snapMode));
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
    <svg ref={svgRef} className={`trading-drawing-overlay tool-${tool}`} aria-label="Interactive chart drawings" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
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
        return (
          <g key={drawing.drawingId} data-locked={drawing.locked} onPointerDown={(event) => { event.stopPropagation(); onSelect(drawing.drawingId); }}>
            {drawing.toolType === 'horizontal-line' ? <line {...lineProps} x1="0" x2="100%" y1={first.y} y2={first.y} /> : null}
            {drawing.toolType === 'vertical-line' ? <line {...lineProps} x1={first.x} x2={first.x} y1="0" y2="100%" /> : null}
            {(drawing.toolType === 'trend-line' || drawing.toolType === 'measurement') && second ? <line {...lineProps} x1={first.x} y1={first.y} x2={second.x} y2={second.y} /> : null}
            {drawing.toolType === 'ray' && second ? <line {...lineProps} x1={first.x} y1={first.y} x2="100%" y2={second.y} /> : null}
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
