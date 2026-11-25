// AI range (2026-11, after TradingView's AI Range): drag across a span of the
// chart, then ask about it. The band covers the full chart height, like a date
// range; the AI Range panel opens while it is selected (`TradingAiRangePanel`).
import { DEFAULT_DRAWING_STYLE, defineDrawingTool, type DrawingGeometryContext, type DrawingShape } from '../types';

export const AI_RANGE_TOOL_ID = 'ai-range';

/** The band's violet, unless the person chose a colour. */
export const AI_RANGE_COLOR = '#8e6cef';

function aiRangeGeometry(context: DrawingGeometryContext): DrawingShape[] {
  const [first, second] = context.points;
  const color = context.style.color === DEFAULT_DRAWING_STYLE.color ? AI_RANGE_COLOR : context.style.color;
  const left = Math.min(first.x, second.x);
  const right = Math.max(first.x, second.x);
  const height = Math.max(context.viewport.height, first.y, second.y);
  const edge = { stroke: color, strokeWidth: context.selected ? 1.5 : 1, hit: 'none' } as const;
  return [
    { kind: 'rect', x: left, y: 0, width: Math.max(1, right - left), height, fill: color, fillOpacity: context.selected ? 0.16 : 0.1, className: 'trading-ai-range-band' },
    { kind: 'segment', x1: left, y1: 0, x2: left, y2: height, ...edge },
    { kind: 'segment', x1: right, y1: 0, x2: right, y2: height, ...edge },
    { kind: 'text', x: left + 6, y: 16, text: '✧ AI range', align: 'start', fontSize: 11, fontWeight: 600, fill: color, hit: 'none', className: 'trading-ai-range-label' },
  ];
}

export const aiRangeTool = defineDrawingTool({
  id: AI_RANGE_TOOL_ID,
  label: 'AI range',
  icon: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z',
  group: 'measurers',
  creation: { gesture: 'drag' },
  defaultProperties: {},
  propertySchema: [],
  draftPreview: 'shapes',
  geometry: aiRangeGeometry,
});
