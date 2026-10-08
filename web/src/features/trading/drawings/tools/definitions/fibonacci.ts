import { lineStroke } from '../shapes';
import { defineDrawingTool, type DrawingShape } from '../types';

export const FIBONACCI_RETRACEMENT_LEVELS: readonly number[] = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

function levelsFrom(value: unknown): readonly number[] {
  return Array.isArray(value) ? value.filter((level): level is number => typeof level === 'number' && Number.isFinite(level)) : FIBONACCI_RETRACEMENT_LEVELS;
}

export const fibonacciTool = defineDrawingTool({
  id: 'fibonacci',
  label: 'Fib retracement',
  group: 'fibonacci',
  creation: { gesture: 'drag' },
  defaultProperties: { levels: FIBONACCI_RETRACEMENT_LEVELS, showLabels: true, extendLeft: false, extendRight: false },
  propertySchema: [
    { key: 'levels', label: 'Levels', type: 'number-list' },
    { key: 'showLabels', label: 'Labels', type: 'boolean' },
    { key: 'extendLeft', label: 'Extend left', type: 'boolean' },
    { key: 'extendRight', label: 'Extend right', type: 'boolean' },
  ],
  geometry: (context) => {
    const [first, second] = context.points;
    const stroke = lineStroke(context);
    const left = Math.min(first.x, second.x);
    const right = Math.max(first.x, second.x);
    const x1 = context.properties.extendLeft === true ? 0 : left;
    const x2 = context.properties.extendRight === true ? context.viewport.width : right;
    const showLabels = context.properties.showLabels !== false;
    return levelsFrom(context.properties.levels).flatMap((level): DrawingShape[] => {
      const y = first.y + (second.y - first.y) * level;
      const line: DrawingShape = { kind: 'segment', x1, y1: y, x2, y2: y, ...stroke };
      return showLabels ? [line, { kind: 'text', x: right + 4, y: y - 2, text: String(level) }] : [line];
    });
  },
});
