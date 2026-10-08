import { DRAWING_HIT_TOLERANCE, hitTestShapes } from './hitTest';
import {
  anchorCount,
  type DrawingGeometryContext,
  type DrawingHit,
  type DrawingPoint,
  type DrawingShape,
  type DrawingToolDefinition,
  type ScreenPoint,
} from './types';

export type DrawingProjector = (point: DrawingPoint) => ScreenPoint | null;

export type DrawingShapeInput = Omit<DrawingGeometryContext, 'points' | 'project'> & {
  definition: DrawingToolDefinition;
  project: DrawingProjector;
};

/**
 * Projects a drawing's anchors and runs its geometry. Returns no shapes (and
 * a null context) until the tool has its minimum anchors and all of them
 * project onto the chart.
 */
export function drawingGeometry(input: DrawingShapeInput): { shapes: DrawingShape[]; context: DrawingGeometryContext | null } {
  const { definition, project, rawPoints } = input;
  if (rawPoints.length < anchorCount(definition.creation).min) return { shapes: [], context: null };
  const points: ScreenPoint[] = [];
  for (const point of rawPoints) {
    const projected = project(point);
    if (!projected) return { shapes: [], context: null };
    points.push(projected);
  }
  const context: DrawingGeometryContext = {
    points,
    rawPoints,
    viewport: input.viewport,
    style: input.style,
    properties: input.properties,
    text: input.text,
    interval: input.interval,
    selected: input.selected,
    locked: input.locked,
    draft: input.draft,
    project,
  };
  return { shapes: definition.geometry(context), context };
}

/** Hit-tests one drawing's shapes, through the tool's override when it has one. */
export function hitTestDrawing(
  definition: DrawingToolDefinition,
  shapes: readonly DrawingShape[],
  context: DrawingGeometryContext,
  point: ScreenPoint,
  tolerance = DRAWING_HIT_TOLERANCE,
): DrawingHit | null {
  return definition.hitTest
    ? definition.hitTest(shapes, point, tolerance, context)
    : hitTestShapes(shapes, point, tolerance);
}
