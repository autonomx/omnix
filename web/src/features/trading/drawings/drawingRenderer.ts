// Which host paints drawings (TVP-0.4 renderer decision).
//
// Both hosts paint the same registry shapes. The canvas host (a Lightweight
// Charts series primitive, DrawingCanvasPrimitive) is the target: in the spike
// it cost about half as much per pan frame as SVG with 500 mixed drawings and
// keeps the DOM flat. SVG stays the default until the canvas paint matches the
// themed SVG styles (dot, text halo, light theme, selection glow); TVP-3.4
// checks that by eye and flips the default. To try canvas now, set this
// localStorage key to `canvas` and reload.
export type DrawingRendererMode = 'svg' | 'canvas';

export const DRAWING_RENDERER_STORAGE_KEY = 'omnix.trading.drawing-renderer';

export function storedDrawingRendererMode(): DrawingRendererMode {
  try {
    return window.localStorage.getItem(DRAWING_RENDERER_STORAGE_KEY) === 'canvas' ? 'canvas' : 'svg';
  } catch {
    return 'svg';
  }
}
