import { useEffect, useRef, useState } from 'react';
import { simplifyPolyline } from './tools/shapes';
import { anchorCount, type DrawingPoint, type DrawingToolDefinition, type ScreenPoint } from './tools/types';

export type PointerPoint = DrawingPoint & ScreenPoint;

/** Minimum pointer travel, in pixels, before a freehand stroke takes another point. */
const FREEHAND_STEP = 2;

function anchor(point: PointerPoint): DrawingPoint {
  return { time: point.time, price: point.price };
}

/**
 * Creation gestures for every tool, driven by its `creation` declaration. The
 * draft holds the anchors placed so far; for drag and click-click its last
 * anchor follows the pointer.
 */
export function useDrawingCreation(definition: DrawingToolDefinition | undefined, complete: (points: DrawingPoint[]) => void) {
  const [draft, setDraft] = useState<PointerPoint[] | null>(null);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const creation = definition?.creation;

  useEffect(() => {
    setDraft(null);
  }, [definition]);

  useEffect(() => {
    if (!draft || creation?.gesture !== 'click-click') return;
    const cancel = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDraft(null);
    };
    window.addEventListener('keydown', cancel);
    return () => window.removeEventListener('keydown', cancel);
  }, [draft, creation]);

  const finish = (points: PointerPoint[]) => {
    setDraft(null);
    complete(points.map(anchor));
  };

  /** Returns true when the pointer down started or continued a gesture. */
  const pointerDown = (point: PointerPoint): boolean => {
    if (!creation) return false;
    switch (creation.gesture) {
      case 'click':
        finish([point]);
        return true;
      case 'drag':
      case 'freehand':
        setDraft([point, ...(creation.gesture === 'drag' ? [point] : [])]);
        return true;
      case 'click-click': {
        const placed = draftRef.current ? [...draftRef.current.slice(0, -1), point] : [point];
        const { max } = anchorCount(creation);
        if (max !== null && placed.length >= max) finish(placed);
        else setDraft([...placed, point]);
        return true;
      }
    }
  };

  const pointerMove = (point: PointerPoint) => {
    const current = draftRef.current;
    if (!current || !creation) return;
    if (creation.gesture === 'freehand') {
      const last = current[current.length - 1];
      if (Math.hypot(point.x - last.x, point.y - last.y) >= FREEHAND_STEP) setDraft([...current, point]);
      return;
    }
    setDraft([...current.slice(0, -1), point]);
  };

  const pointerUp = () => {
    const current = draftRef.current;
    if (!current || !creation) return;
    if (creation.gesture === 'drag') {
      finish(current);
    } else if (creation.gesture === 'freehand') {
      const points = simplifyPolyline(current, creation.simplifyTolerance ?? 1);
      if (points.length >= anchorCount(creation).min) finish(points);
      else setDraft(null);
    }
  };

  /** Completes an open-ended click-click drawing. */
  const doubleClick = () => {
    const current = draftRef.current;
    if (!current || creation?.gesture !== 'click-click' || creation.anchors !== undefined) return;
    // The double click's two pointer downs placed its anchor twice, plus the floating one.
    const placed = current.slice(0, -2);
    if (placed.length >= anchorCount(creation).min) finish(placed);
  };

  return { draft, pointerDown, pointerMove, pointerUp, doubleClick };
}
