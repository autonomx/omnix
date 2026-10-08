import { lineAlertLevel } from '../alertLevels';
import { extendedSegment, lineStroke, rayEnd } from '../shapes';
import { booleanProperty } from '../properties';
import { defineDrawingTool, type DrawingAlertLevel } from '../types';

export const trendLineTool = defineDrawingTool({
  id: 'trend-line',
  label: 'Trend line',
  displayName: 'Trendline',
  group: 'lines',
  creation: { gesture: 'drag' },
  defaultProperties: { extendLeft: false, extendRight: false },
  propertySchema: [
    { key: 'extendLeft', label: 'Extend left', type: 'boolean' },
    { key: 'extendRight', label: 'Extend right', type: 'boolean' },
  ],
  geometry: (context) => {
    const [first, second] = context.points;
    const [start, end] = extendedSegment(
      first,
      second,
      context.viewport,
      booleanProperty(context.properties, 'extendLeft', false),
      booleanProperty(context.properties, 'extendRight', false),
    );
    return [{ kind: 'segment', x1: start.x, y1: start.y, x2: end.x, y2: end.y, ...lineStroke(context) }];
  },
  alertLevels: ([first, second], properties) => {
    if (!first || !second) return [];
    const level = lineAlertLevel(
      'line',
      'Trend line',
      first,
      second,
      booleanProperty(properties, 'extendLeft', false),
      booleanProperty(properties, 'extendRight', false),
    );
    return level ? [level] : [];
  },
});

export const rayTool = defineDrawingTool({
  id: 'ray',
  label: 'Ray',
  group: 'lines',
  creation: { gesture: 'drag' },
  defaultProperties: {},
  propertySchema: [],
  geometry: (context) => {
    const [first, second] = context.points;
    const end = rayEnd(first, second, context.viewport);
    return [{ kind: 'segment', x1: first.x, y1: first.y, x2: end.x, y2: end.y, ...lineStroke(context) }];
  },
  alertLevels: ([first, second]): DrawingAlertLevel[] => {
    if (!first || !second) return [];
    const rightward = Date.parse(second.time) > Date.parse(first.time);
    const level = lineAlertLevel('ray', 'Ray', first, second, !rightward, rightward);
    return level ? [level] : [];
  },
});
