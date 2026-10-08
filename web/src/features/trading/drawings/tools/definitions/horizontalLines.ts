import { horizontalAlertLevel } from '../alertLevels';
import { lineStroke } from '../shapes';
import { defineDrawingTool } from '../types';

export const horizontalLineTool = defineDrawingTool({
  id: 'horizontal-line',
  label: 'Horizontal line',
  group: 'lines',
  creation: { gesture: 'click' },
  defaultProperties: {},
  propertySchema: [],
  geometry: (context) => {
    const [point] = context.points;
    return [{ kind: 'segment', x1: 0, y1: point.y, x2: context.viewport.width, y2: point.y, ...lineStroke(context) }];
  },
  alertLevels: ([point]) => (point ? [horizontalAlertLevel('line', 'Horizontal line', point, null)] : []),
});

export const horizontalRayTool = defineDrawingTool({
  id: 'horizontal-ray',
  label: 'Horizontal ray',
  group: 'lines',
  creation: { gesture: 'click' },
  defaultProperties: {},
  propertySchema: [],
  geometry: (context) => {
    const [point] = context.points;
    return [{ kind: 'segment', x1: point.x, y1: point.y, x2: context.viewport.width, y2: point.y, ...lineStroke(context) }];
  },
  alertLevels: ([point]) => (point ? [horizontalAlertLevel('ray', 'Horizontal ray', point, point.time)] : []),
});
