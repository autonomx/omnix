import { useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { DrawingPoint, DrawingTool, TradingDrawing } from './drawingCommands';
import type { PointerPoint } from './useDrawingCreation';

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
    const timeDelta = Date.parse(translation.to.time) - Date.parse(translation.from.time);
    const priceDelta = translation.to.price - translation.from.price;
    points = points.map((point) => ({
      time: new Date(Date.parse(point.time) + timeDelta).toISOString(),
      price: point.price + priceDelta,
    }));
  }
  if (handle?.drawingId === drawing.drawingId) {
    points = points.map((point, index) => index === handle.index ? handle.point : point);
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

/** Handle drags, whole-drawing drags, selection and erasing on existing drawings. */
export function useDrawingEditing({
  tool,
  enabled,
  pointFromClient,
  onSelect,
  onMovePoint,
  onTranslateDrawing,
  onRemove,
  onToolComplete,
}: {
  tool: DrawingTool;
  enabled: boolean;
  pointFromClient: (clientX: number, clientY: number) => PointerPoint | null;
  onSelect: (id: string | null) => void;
  onMovePoint: (id: string, index: number, point: DrawingPoint) => void;
  onTranslateDrawing: (id: string, from: DrawingPoint, to: DrawingPoint) => void;
  onRemove: (id: string) => void;
  onToolComplete?: () => void;
}) {
  const [handlePreview, setHandlePreview] = useState<HandlePreview | null>(null);
  const [translationPreview, setTranslationPreview] = useState<TranslationPreview | null>(null);
  const anchorAt = (clientX: number, clientY: number): DrawingPoint | null => {
    const point = pointFromClient(clientX, clientY);
    return point ? { time: point.time, price: point.price } : null;
  };

  const dragHandle = (drawing: TradingDrawing, index: number) => (event: ReactPointerEvent<SVGElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (drawing.locked || !enabled) return;
    trackPointer((pointer) => {
      const point = anchorAt(pointer.clientX, pointer.clientY);
      if (point) setHandlePreview({ drawingId: drawing.drawingId, index, point });
    }, (pointer) => {
      const point = anchorAt(pointer.clientX, pointer.clientY);
      setHandlePreview(null);
      if (point) onMovePoint(drawing.drawingId, index, point);
    });
  };

  /** Pointer down on a drawing: erase it, or select it and (with the cursor) start moving it. */
  const pressDrawing = (drawing: TradingDrawing, clientX: number, clientY: number) => {
    if (tool === 'eraser') {
      onRemove(drawing.drawingId);
      onToolComplete?.();
      return;
    }
    onSelect(drawing.drawingId);
    if (tool !== 'cursor' || drawing.locked || !enabled) return;
    const start = anchorAt(clientX, clientY);
    if (!start) return;
    trackPointer((pointer) => {
      const point = anchorAt(pointer.clientX, pointer.clientY);
      if (point) setTranslationPreview({ drawingId: drawing.drawingId, from: start, to: point });
    }, (pointer) => {
      const point = anchorAt(pointer.clientX, pointer.clientY);
      setTranslationPreview(null);
      if (point && (point.time !== start.time || point.price !== start.price)) {
        onTranslateDrawing(drawing.drawingId, start, point);
      }
    });
  };

  const dragDrawing = (drawing: TradingDrawing) => (event: ReactPointerEvent<SVGElement>) => {
    event.preventDefault();
    event.stopPropagation();
    pressDrawing(drawing, event.clientX, event.clientY);
  };

  return { handlePreview, translationPreview, dragHandle, dragDrawing, pressDrawing };
}
