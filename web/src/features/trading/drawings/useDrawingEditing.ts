import { useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { DrawingPoint, DrawingProperties, DrawingTool, TradingDrawing } from './drawingCommands';
import { guardToolCall } from './tools/guard';
import { drawingPropertiesWithDefaults } from './tools/registry';
import type { DrawingEditPatch, DrawingHandle, DrawingModifiers, DrawingToolServices, ScreenPoint } from './tools/types';

export type HandlePreview = { drawingId: string; patch: DrawingEditPatch };
export type TranslationPreview = { drawingId: string; from: DrawingPoint; to: DrawingPoint };

/** A drawing's anchors and properties with an in-progress translation or handle drag applied. */
export function previewDrawing(
  drawing: TradingDrawing,
  translation: TranslationPreview | null,
  handle: HandlePreview | null,
): { points: DrawingPoint[]; properties: DrawingProperties | undefined } {
  let points = drawing.points;
  let properties = drawing.properties;
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
    if (handle.patch.points) points = [...handle.patch.points];
    if (handle.patch.properties) properties = { ...properties, ...handle.patch.properties };
  }
  return { points, properties };
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

/** Whether a handle's edit changes the drawing; a pixel of jitter that snaps back to the same anchor does not. */
export function patchChanges(drawing: TradingDrawing, patch: DrawingEditPatch): boolean {
  const same = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);
  if (patch.points && !same(patch.points, drawing.points)) return true;
  if (!patch.properties) return false;
  const current = drawingPropertiesWithDefaults(drawing.toolType, drawing.properties);
  return Object.entries(patch.properties).some(([key, value]) => !same(value, current[key]));
}

export function modifiersOf(event: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): DrawingModifiers {
  return { shift: event.shiftKey, alt: event.altKey, ctrl: event.ctrlKey || event.metaKey };
}

/** The chart point under the pointer for one of a drawing's anchors (`anchorIndex`, Shift-constrained), or for the drawing as a whole. */
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
  screenFor,
  services,
  onSelect,
  onEdit,
  onTranslateDrawing,
  onRemove,
  onToolComplete,
}: {
  tool: DrawingTool;
  enabled: boolean;
  pointFor: DrawingPointLocator;
  /** The pointer in pane pixels. */
  screenFor: (clientX: number, clientY: number) => ScreenPoint | null;
  services: () => DrawingToolServices;
  onSelect: (id: string | null) => void;
  onEdit: (id: string, patch: DrawingEditPatch) => void;
  onTranslateDrawing: (id: string, from: DrawingPoint, to: DrawingPoint) => void;
  onRemove: (id: string) => void;
  onToolComplete?: () => void;
}) {
  const [handlePreview, setHandlePreview] = useState<HandlePreview | null>(null);
  const [translationPreview, setTranslationPreview] = useState<TranslationPreview | null>(null);
  const edits = toolEditsDrawings(tool);

  /** The edit a handle makes with the pointer at (clientX, clientY). */
  const handlePatch = (drawing: TradingDrawing, handle: DrawingHandle, pointer: PointerEvent): DrawingEditPatch | null => {
    const modifiers = modifiersOf(pointer);
    const point = pointFor(drawing, pointer.clientX, pointer.clientY, modifiers, handle.anchorIndex);
    const screen = screenFor(pointer.clientX, pointer.clientY);
    if (!point || !screen) return null;
    const input = {
      points: drawing.points,
      properties: drawingPropertiesWithDefaults(drawing.toolType, drawing.properties),
      point,
      screen,
      modifiers,
      services: services(),
    };
    return guardToolCall(drawing.toolType, 'handle drag', () => handle.drag(input), null);
  };

  const dragHandle = (drawing: TradingDrawing, handle: DrawingHandle) => (event: ReactPointerEvent<SVGElement>) => {
    if (!edits) return;
    event.preventDefault();
    event.stopPropagation();
    if (drawing.locked || !enabled) return;
    // A click on a handle without moving it edits nothing, so it adds no undo step.
    const start = { x: event.clientX, y: event.clientY };
    let moved = false;
    const movedFrom = (pointer: PointerEvent) => pointer.clientX !== start.x || pointer.clientY !== start.y;
    trackPointer((pointer) => {
      moved ||= movedFrom(pointer);
      if (!moved) return;
      const patch = handlePatch(drawing, handle, pointer);
      if (patch) setHandlePreview({ drawingId: drawing.drawingId, patch });
    }, (pointer) => {
      setHandlePreview(null);
      if (!moved && !movedFrom(pointer)) return;
      const patch = handlePatch(drawing, handle, pointer);
      if (patch && patchChanges(drawing, patch)) onEdit(drawing.drawingId, patch);
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
