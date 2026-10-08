// The drawing tool registry (TVP-0.4). To add a tool, write one module in
// `definitions/` and list it here; hosts and the toolbar pick it up from here.
import { arrowTool } from './definitions/arrow';
import { anchoredVwapTool, regressionTrendTool } from './definitions/barTools';
import { circleTool, ellipseTool, rectangleTool } from './definitions/boxShapes';
import { disjointChannelTool, flatTopBottomTool, parallelChannelTool } from './definitions/channels';
import { dotTool } from './definitions/dot';
import { fibonacciTool } from './definitions/fibonacci';
import { horizontalLineTool, horizontalRayTool } from './definitions/horizontalLines';
import { extendedLineTool, infoLineTool, trendAngleTool } from './definitions/lineVariants';
import { measurementTool } from './definitions/measurement';
import { textTool } from './definitions/text';
import { rayTool, trendLineTool } from './definitions/trendLines';
import { crosslineTool, verticalLineTool } from './definitions/verticalLines';
import type { DrawingProperties, DrawingPropertyValue, DrawingToolDefinition } from './types';

export const DRAWING_TOOL_DEFINITIONS = [
  dotTool,
  arrowTool,
  horizontalLineTool,
  horizontalRayTool,
  trendLineTool,
  verticalLineTool,
  crosslineTool,
  rayTool,
  infoLineTool,
  extendedLineTool,
  trendAngleTool,
  parallelChannelTool,
  regressionTrendTool,
  flatTopBottomTool,
  disjointChannelTool,
  anchoredVwapTool,
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

/**
 * A drawing's properties with the tool's defaults filled in for missing keys.
 * Stored values are kept as they are, even when they don't match the schema,
 * so nothing written by another client version is lost; geometry reads them
 * defensively (`properties.ts`).
 */
export function drawingPropertiesWithDefaults(toolType: string, stored: DrawingProperties | undefined): DrawingProperties {
  const definition = byId.get(toolType);
  const properties: Record<string, DrawingPropertyValue> = { ...(stored ?? {}) };
  if (!definition) return properties;
  for (const [key, fallback] of Object.entries(definition.defaultProperties)) {
    if (properties[key] === undefined) properties[key] = Array.isArray(fallback) ? [...fallback] : fallback;
  }
  return properties;
}

/** The object-tree name of a drawing: its text for text tools, the tool's name otherwise. */
export function drawingDisplayName(drawing: { toolType: string; text?: string }): string {
  const definition = byId.get(drawing.toolType);
  if (!definition) return `${drawing.toolType} (unsupported)`;
  if (definition.editableText && drawing.text) return drawing.text;
  return definition.displayName ?? definition.label;
}
