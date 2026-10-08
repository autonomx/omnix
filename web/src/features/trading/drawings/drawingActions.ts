// The drawing action bus (TVP-0.4): a tool's context-menu action produces a
// request (`{ type, payload }`); a feature that can act on that type (the
// order ticket for `order-ticket`, say) subscribes here. Neither the context
// menu nor the chart panel knows any action.
import type { DrawingActionRequest } from './tools/types';

type DrawingActionHandler = (payload: unknown) => void;

const handlers = new Map<string, Set<DrawingActionHandler>>();

/** Handles requests of one type until the returned function is called. */
export function onDrawingActionRequest(type: string, handler: DrawingActionHandler): () => void {
  const set = handlers.get(type) ?? new Set<DrawingActionHandler>();
  set.add(handler);
  handlers.set(type, set);
  return () => {
    set.delete(handler);
    if (set.size === 0) handlers.delete(type);
  };
}

/** Whether any feature currently handles requests of this type (the menu disables actions nobody handles). */
export function hasDrawingActionHandler(type: string): boolean {
  return (handlers.get(type)?.size ?? 0) > 0;
}

/** Hands a request to its handlers; false when none is listening. */
export function dispatchDrawingActionRequest(request: DrawingActionRequest): boolean {
  const set = handlers.get(request.type);
  if (!set || set.size === 0) return false;
  for (const handler of [...set]) handler(request.payload);
  return true;
}
