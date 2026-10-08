import { useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { DrawingPoint, DrawingTool, TradingDrawing } from './drawingCommands';
import type { DrawingModifiers } from './tools/types';

export type HandlePreview = { drawingId: string; index: number; point: DrawingPoint };
export type TranslationPreview = { drawingId: string; from: DrawingPoint; to: DrawingPoint };

/** A drawing's anchors with an in-progress translation or handle drag applied. */
export function previewPoints(
  drawing: TradingDrawing,
  translation: TranslationPreview | null,
  handle: HandlePreview | null,
): DrawingPoint[] {
  let points = drawing.points;
  if (translation?.drawingId === drawing.drawingId) {
    const { from, to } = translation;
    const timeDelta = Date.parse(to.time) - Date.parse(from.time);
    const priceDelta = to.price - from.price;
    points = points.map((point) => ({
      ...point,
      time: new Date(Date.parse(point.time) + timeDelta).toISOString(),
      price: point.price + priceDelta,
      ...(point.screen && from.screen && to.screen
        ? { screen: { x: point.screen.x + to.screen.x - from.screen.x, y: point.screen.y + to.screen.y - from.screen.y } }
        : {}),
    }));
  }
  if (handle?.drawingId === drawing.drawingId) {
    points = points.map((point, index) => index === handle.index ? { ...point, ...handle.point } : point);
  }
  return points;
}

function trackPointer(move: (event: PointerEvent) => void, up: (event: PointerEvent) => void): void {
  const release = (event: PointerEvent) => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', release);
    up(event);
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', release);
}

/** Whether presses on existing drawings edit them; with any other tool they start or continue a creation. */
export function toolEditsDrawings(tool: DrawingTool): boolean {
  return tool === 'cursor' || tool === 'eraser';
}

export function modifiersOf(event: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): DrawingModifiers {
  return { shift: event.shiftKey, alt: event.altKey, ctrl: event.ctrlKey || event.metaKey };
}

/** The chart point under the pointer for one of a drawing's anchors (`anchorIndex`), or for the drawing as a whole. */
export type DrawingPointLocator = (
  drawing: TradingDrawing,
  clientX: number,
  clientY: number,
  modifiers: DrawingModifiers,
  anchorIndex?: number,
) => DrawingPoint | null;

/**
 * Handle drags, whole-drawing drags, selection and erasing on existing
 * drawings, for the cursor and eraser. Any other tool lets presses fall
 * through to creation, so anchors can be placed on top of drawings.
 */
export function useDrawingEditing({
  tool,
  enabled,
  pointFor,
  onSelect,
  onMovePoint,
  onTranslateDrawing,
  onRemove,
  onToolComplete,
}: {
  tool: DrawingTool;
  enabled: boolean;
  pointFor: DrawingPointLocator;
  onSelect: (id: string | null) => void;
  onMovePoint: (id: string, index: number, point: DrawingPoint) => void;
  onTranslateDrawing: (id: string, from: DrawingPoint, to: DrawingPoint) => void;
  onRemove: (id: string) => void;
  onToolComplete?: () => void;
}) {
  const [handlePreview, setHandlePreview] = useState<HandlePreview | null>(null);
  const [translationPreview, setTranslationPreview] = useState<TranslationPreview | null>(null);
  const edits = toolEditsDrawings(tool);

  const dragHandle = (drawing: TradingDrawing, index: number) => (event: ReactPointerEvent<SVGElement>) => {
    if (!edits) return;
    event.preventDefault();
    event.stopPropagation();
    if (drawing.locked || !enabled) return;
    trackPointer((pointer) => {
      const point = pointFor(drawing, pointer.clientX, pointer.clientY, modifiersOf(pointer), index);
      if (point) setHandlePreview({ drawingId: drawing.drawingId, index, point });
    }, (pointer) => {
      const point = pointFor(drawing, pointer.clientX, pointer.clientY, modifiersOf(pointer), index);
      setHandlePreview(null);
      if (point) onMovePoint(drawing.drawingId, index, { ...drawing.points[index], ...point });
    });
  };

  /** Pointer down on a drawing with the eraser or cursor: erase it, or select it and start moving it. */
  const pressDrawing = (drawing: TradingDrawing, clientX: number, clientY: number, modifiers: DrawingModifiers) => {
    if (tool === 'eraser') {
      onRemove(drawing.drawingId);
      onToolComplete?.();
      return;
    }
    onSelect(drawing.drawingId);
    if (drawing.locked || !enabled) return;
    const start = pointFor(drawing, clientX, clientY, modifiers);
    if (!start) return;
    trackPointer((pointer) => {
      const point = pointFor(drawing, pointer.clientX, pointer.clientY, modifiersOf(pointer));
      if (point) setTranslationPreview({ drawingId: drawing.drawingId, from: start, to: point });
    }, (pointer) => {
      const point = pointFor(drawing, pointer.clientX, pointer.clientY, modifiersOf(pointer));
      setTranslationPreview(null);
      const moved = point && (point.time !== start.time || point.price !== start.price
        || point.screen?.x !== start.screen?.x || point.screen?.y !== start.screen?.y);
      if (point && moved) onTranslateDrawing(drawing.drawingId, start, point);
    });
  };

  const dragDrawing = (drawing: TradingDrawing) => (event: ReactPointerEvent<SVGElement>) => {
    if (!edits) return;
    event.preventDefault();
    event.stopPropagation();
    pressDrawing(drawing, event.clientX, event.clientY, modifiersOf(event));
  };

  return { handlePreview, translationPreview, dragHandle, dragDrawing, edits };
}
