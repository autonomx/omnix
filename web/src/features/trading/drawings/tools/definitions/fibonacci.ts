import { horizontalAlertLevel } from '../alertLevels';
import { booleanProperty, recordsProperty } from '../properties';
import { lineStroke } from '../shapes';
import { defineDrawingTool, type DrawingPropertyRecord, type DrawingShape } from '../types';

export const FIBONACCI_RETRACEMENT_LEVELS: readonly number[] = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

/** One level per record: `value`, `visible`, and `color` ('' = the drawing's colour). */
const DEFAULT_LEVELS: readonly DrawingPropertyRecord[] = FIBONACCI_RETRACEMENT_LEVELS.map((value) => ({ value, color: '', visible: true }));

export const fibonacciTool = defineDrawingTool({
  id: 'fibonacci',
  label: 'Fib retracement',
  displayName: 'Fib Retracement',
  group: 'fibonacci',
  creation: { gesture: 'drag' },
  defaultProperties: { levels: DEFAULT_LEVELS, showLabels: true, extendLeft: false, extendRight: false },
  propertySchema: [
    {
      key: 'levels',
      label: 'Levels',
      type: 'records',
      fields: [
        { key: 'value', label: 'Level', type: 'number', step: 0.001 },
        { key: 'color', label: 'Colour', type: 'color' },
        { key: 'visible', label: 'Visible', type: 'boolean' },
      ],
      newRecord: { value: 1.618, color: '', visible: true },
    },
    { key: 'showLabels', label: 'Labels', type: 'boolean' },
    { key: 'extendLeft', label: 'Extend left', type: 'boolean' },
    { key: 'extendRight', label: 'Extend right', type: 'boolean' },
  ],
  geometry: (context) => {
    const [first, second] = context.points;
    const stroke = lineStroke(context);
    const left = Math.min(first.x, second.x);
    const right = Math.max(first.x, second.x);
    const x1 = booleanProperty(context.properties, 'extendLeft', false) ? 0 : left;
    const x2 = booleanProperty(context.properties, 'extendRight', false) ? context.viewport.width : right;
    const showLabels = booleanProperty(context.properties, 'showLabels', true);
    return recordsProperty(context.properties, 'levels', DEFAULT_LEVELS).flatMap((record): DrawingShape[] => {
      const level = record.value;
      if (typeof level !== 'number' || !Number.isFinite(level) || record.visible === false) return [];
      const y = first.y + (second.y - first.y) * level;
      const color = typeof record.color === 'string' && record.color ? record.color : stroke.stroke;
      const line: DrawingShape = { kind: 'segment', x1, y1: y, x2, y2: y, ...stroke, stroke: color };
      return showLabels ? [line, { kind: 'text', x: right + 4, y: y - 2, text: String(level) }] : [line];
    });
  },
  // Each visible level as a level from the drawing's left edge onwards (TVP-1.4).
  alertLevels: ([first, second], properties, services) => {
    if (!first || !second) return [];
    const left = Date.parse(first.time) <= Date.parse(second.time) ? first.time : second.time;
    // Keyed by value: removing or reordering levels keeps each alert on its level; editing a level's value takes
    // its alerts off it (they are offered for disabling), never onto another level.
    const seen = new Map<number, number>();
    return recordsProperty(properties, 'levels', DEFAULT_LEVELS).flatMap((record) => {
      const level = record.value;
      if (typeof level !== 'number' || !Number.isFinite(level)) return [];
      const count = (seen.get(level) ?? 0) + 1;
      seen.set(level, count);
      if (record.visible === false) return [];
      const price = first.price + (second.price - first.price) * level;
      const key = count === 1 ? `level-${level}` : `level-${level}-${count}`;
      const alertLevel = horizontalAlertLevel(key, `Level ${level} (${services.formatPrice(price)})`, { time: left, price }, 'right', services);
      return alertLevel ? [alertLevel] : [];
    });
  },
});
