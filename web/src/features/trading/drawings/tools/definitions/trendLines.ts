import { lineAlertLevel } from '../alertLevels';
import { extendedSegment, lineStroke, rayEnd } from '../shapes';
import { defineDrawingTool, type DrawingAlertLevel } from '../types';

export const trendLineTool = defineDrawingTool({
  id: 'trend-line',
  label: 'Trend line',
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
      context.properties.extendLeft === true,
      context.properties.extendRight === true,
    );
    return [{ kind: 'segment', x1: start.x, y1: start.y, x2: end.x, y2: end.y, ...lineStroke(context) }];
  },
  alertLevels: ([first, second], properties) => {
    if (!first || !second) return [];
    const level = lineAlertLevel('line', 'Trend line', first, second, properties.extendLeft === true, properties.extendRight === true);
    return level ? [level] : [];
  },
  lineAlertAnchors: (points) => points.slice(0, 2),
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
