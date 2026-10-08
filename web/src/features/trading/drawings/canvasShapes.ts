// Canvas 2D rendering of drawing shapes (TVP-0.4 renderer spike). Paints the
// same `DrawingShape[]` the SVG host renders, in CSS-pixel (media) space.
import type { DrawingShape, PathCommand } from './tools/types';

const DEFAULT_TEXT_COLOR = '#e2e8f0';
const SELECTED_GLOW = '#ffd43b';

function tracePath(context: CanvasRenderingContext2D, commands: readonly PathCommand[]): void {
  for (const command of commands) {
    switch (command.op) {
      case 'M':
        context.moveTo(command.x, command.y);
        break;
      case 'L':
        context.lineTo(command.x, command.y);
        break;
      case 'Q':
        context.quadraticCurveTo(command.cx, command.cy, command.x, command.y);
        break;
      case 'C':
        context.bezierCurveTo(command.c1x, command.c1y, command.c2x, command.c2y, command.x, command.y);
        break;
      case 'Z':
        context.closePath();
        break;
    }
  }
}

function traceShape(context: CanvasRenderingContext2D, shape: Exclude<DrawingShape, { kind: 'text' }>): void {
  context.beginPath();
  switch (shape.kind) {
    case 'segment':
      context.moveTo(shape.x1, shape.y1);
      context.lineTo(shape.x2, shape.y2);
      break;
    case 'polyline':
    case 'polygon': {
      const { points } = shape;
      if (points.length === 0) break;
      context.moveTo(points[0].x, points[0].y);
      for (let index = 1; index < points.length; index += 1) context.lineTo(points[index].x, points[index].y);
      if (shape.kind === 'polygon') context.closePath();
      break;
    }
    case 'rect':
      if (shape.radius) context.roundRect(shape.x, shape.y, shape.width, shape.height, shape.radius);
      else context.rect(shape.x, shape.y, shape.width, shape.height);
      break;
    case 'ellipse':
      context.ellipse(shape.cx, shape.cy, Math.max(0, shape.rx), Math.max(0, shape.ry), 0, 0, Math.PI * 2);
      break;
    case 'path':
      tracePath(context, shape.commands);
      break;
    case 'marker':
      context.arc(shape.x, shape.y, Math.max(0, shape.radius), 0, Math.PI * 2);
      break;
  }
}

function paintShape(context: CanvasRenderingContext2D, shape: DrawingShape): void {
  const selected = shape.className?.split(' ').includes('selected') ?? false;
  context.globalAlpha = shape.opacity ?? 1;
  if (selected) {
    context.shadowColor = SELECTED_GLOW;
    context.shadowBlur = 3;
  }
  if (shape.kind === 'text') {
    context.font = `${shape.fontWeight ?? 400} ${shape.fontSize ?? 11}px sans-serif`;
    context.textAlign = shape.align === 'middle' ? 'center' : shape.align === 'end' ? 'right' : 'left';
    context.textBaseline = 'alphabetic';
    context.fillStyle = shape.fill ?? DEFAULT_TEXT_COLOR;
    context.fillText(shape.text, shape.x, shape.y);
  } else {
    traceShape(context, shape);
    if (shape.fill !== undefined && shape.fill !== 'none' && shape.fill !== 'transparent') {
      context.globalAlpha = (shape.opacity ?? 1) * (shape.fillOpacity ?? 1);
      context.fillStyle = shape.fill;
      context.fill();
      context.globalAlpha = shape.opacity ?? 1;
    }
    if (shape.stroke !== undefined && shape.stroke !== 'none') {
      context.strokeStyle = shape.stroke;
      context.lineWidth = shape.strokeWidth ?? 1;
      context.setLineDash(shape.dash ? [...shape.dash] : []);
      context.stroke();
    }
  }
  if (selected) {
    context.shadowColor = 'transparent';
    context.shadowBlur = 0;
  }
}

/** Paints shapes in order. The context's state is restored afterwards. */
export function paintShapes(context: CanvasRenderingContext2D, shapes: readonly DrawingShape[]): void {
  context.save();
  context.lineJoin = 'round';
  for (const shape of shapes) paintShape(context, shape);
  context.restore();
}
