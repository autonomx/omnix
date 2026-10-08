// SVG rendering of drawing shapes (TVP-0.4). `ShapeElement` renders a shape
// through React; `patchShapeElement` moves an already-mounted element to new
// coordinates without React, so drawings follow the chart in the same frame.
import type { CSSProperties, SVGProps } from 'react';
import type { DrawingShape, PathCommand, ScreenPoint } from './tools/types';

export function svgPoints(points: readonly ScreenPoint[]): string {
  let value = '';
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    value += `${index === 0 ? '' : ' '}${point.x},${point.y}`;
  }
  return value;
}

export function svgPathData(commands: readonly PathCommand[]): string {
  return commands.map((command) => {
    switch (command.op) {
      case 'M':
      case 'L':
        return `${command.op} ${command.x} ${command.y}`;
      case 'Q':
        return `Q ${command.cx} ${command.cy} ${command.x} ${command.y}`;
      case 'C':
        return `C ${command.c1x} ${command.c1y} ${command.c2x} ${command.c2y} ${command.x} ${command.y}`;
      case 'Z':
        return 'Z';
    }
  }).join(' ');
}

const textAnchor = { start: 'start', middle: 'middle', end: 'end' } as const;
const noPointer: CSSProperties = { pointerEvents: 'none' };

/** The geometry attributes of a shape; the only attributes that change while the chart moves. */
function geometryAttributes(shape: DrawingShape): Record<string, number | string> {
  switch (shape.kind) {
    case 'segment':
      return { x1: shape.x1, y1: shape.y1, x2: shape.x2, y2: shape.y2 };
    case 'polyline':
    case 'polygon':
      return { points: svgPoints(shape.points) };
    case 'rect':
      return { x: shape.x, y: shape.y, width: shape.width, height: shape.height };
    case 'ellipse':
      return { cx: shape.cx, cy: shape.cy, rx: shape.rx, ry: shape.ry };
    case 'path':
      return { d: svgPathData(shape.commands) };
    case 'marker':
      return { cx: shape.x, cy: shape.y, r: shape.radius };
    case 'text':
      return { x: shape.x, y: shape.y };
  }
}

export function ShapeElement({ shape, index }: { shape: DrawingShape; index: number }) {
  const paint: SVGProps<SVGElement> = {
    className: shape.className,
    stroke: shape.stroke,
    strokeWidth: shape.strokeWidth,
    strokeDasharray: shape.dash?.join(' '),
    // Text without a fill keeps the stylesheet's text colour; other shapes are unfilled.
    fill: shape.fill ?? (shape.kind === 'text' ? undefined : 'none'),
    fillOpacity: shape.fillOpacity,
    opacity: shape.opacity,
    style: shape.hit === 'none' ? noPointer : undefined,
  };
  const props = { ...paint, ...geometryAttributes(shape), 'data-shape-index': index };
  switch (shape.kind) {
    case 'segment':
      return <line {...props as SVGProps<SVGLineElement>} />;
    case 'polyline':
      return <polyline {...props as SVGProps<SVGPolylineElement>} />;
    case 'polygon':
      return <polygon {...props as SVGProps<SVGPolygonElement>} />;
    case 'rect':
      return <rect {...props as SVGProps<SVGRectElement>} rx={shape.radius} />;
    case 'ellipse':
      return <ellipse {...props as SVGProps<SVGEllipseElement>} />;
    case 'path':
      return <path {...props as SVGProps<SVGPathElement>} />;
    case 'marker':
      return <circle {...props as SVGProps<SVGCircleElement>} />;
    case 'text':
      return (
        <text
          {...props as SVGProps<SVGTextElement>}
          textAnchor={shape.align ? textAnchor[shape.align] : undefined}
          fontSize={shape.fontSize}
          fontWeight={shape.fontWeight}
        >
          {shape.text}
        </text>
      );
  }
}

/** Moves a mounted shape element to `shape`'s coordinates (and text). */
export function patchShapeElement(element: SVGElement, shape: DrawingShape): void {
  const attributes = geometryAttributes(shape);
  for (const name in attributes) element.setAttribute(name, String(attributes[name]));
  if (shape.kind === 'text' && element.textContent !== shape.text) element.textContent = shape.text;
}
