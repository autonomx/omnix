// The drawing tool registry (TVP-0.4). To add a tool, write one module in
// `definitions/` and list it here; hosts and the toolbar pick it up from here.
import { arrowTool } from './definitions/arrow';
import { circleTool, ellipseTool, rectangleTool } from './definitions/boxShapes';
import { dotTool } from './definitions/dot';
import { fibonacciTool } from './definitions/fibonacci';
import { horizontalLineTool, horizontalRayTool } from './definitions/horizontalLines';
import { measurementTool } from './definitions/measurement';
import { textTool } from './definitions/text';
import { rayTool, trendLineTool } from './definitions/trendLines';
import { crosslineTool, verticalLineTool } from './definitions/verticalLines';
import type { DrawingProperties, DrawingPropertyField, DrawingPropertyValue, DrawingToolDefinition } from './types';

export const DRAWING_TOOL_DEFINITIONS = [
  dotTool,
  arrowTool,
  horizontalLineTool,
  horizontalRayTool,
  trendLineTool,
  verticalLineTool,
  crosslineTool,
  rayTool,
  rectangleTool,
  circleTool,
  ellipseTool,
  fibonacciTool,
  textTool,
  measurementTool,
] as const;

/** Every tool that creates a drawing; the toolbar adds `cursor`, `alert` and `eraser`. */
export type DrawingToolId = (typeof DRAWING_TOOL_DEFINITIONS)[number]['id'];

const byId = new Map<string, DrawingToolDefinition>(DRAWING_TOOL_DEFINITIONS.map((definition) => [definition.id, definition]));

export function drawingToolDefinition(id: string): DrawingToolDefinition | undefined {
  return byId.get(id);
}

export function isDrawingToolId(id: string): id is DrawingToolId {
  return byId.has(id);
}

function valueMatches(field: DrawingPropertyField, value: DrawingPropertyValue): boolean {
  switch (field.type) {
    case 'boolean':
      return typeof value === 'boolean';
    case 'number':
      return typeof value === 'number' && Number.isFinite(value);
    case 'number-list':
      return Array.isArray(value) && value.every((item) => typeof item === 'number' && Number.isFinite(item));
    case 'select':
      return typeof value === 'string' && field.options.some((option) => option.value === value);
    case 'color':
    case 'text':
      return typeof value === 'string';
  }
}

/**
 * A drawing's properties with the tool's defaults filled in. Stored values of
 * the wrong type fall back to the default; keys the tool doesn't declare are
 * kept, so a newer client's properties survive an older one.
 */
export function drawingPropertiesWithDefaults(toolType: string, stored: DrawingProperties | undefined): DrawingProperties {
  const definition = byId.get(toolType);
  if (!definition) return { ...(stored ?? {}) };
  const properties: Record<string, DrawingPropertyValue> = { ...(stored ?? {}) };
  for (const [key, fallback] of Object.entries(definition.defaultProperties)) {
    const field = definition.propertySchema.find((item) => item.key === key);
    const value = properties[key];
    if (value === undefined || (field && !valueMatches(field, value))) {
      properties[key] = Array.isArray(fallback) ? [...fallback] : fallback;
    }
  }
  return properties;
}
