import type { CharacterAvatarPack, CharacterLiveCallRuntime } from './characterClient';
import type { AvatarMouthFrame } from './liveCharacterAvatarBridge';

export type Live2DViseme = 'silence' | 'A' | 'E' | 'O' | 'U' | 'MBP' | 'FV' | 'L' | 'WQ' | 'other';

export type Live2DMouthShape = {
  open: number;
  form: number;
};

type Live2DRenderDetail = {
  runtime: CharacterLiveCallRuntime;
  host: HTMLElement;
};

type RigVisemeDetail = {
  viseme: Live2DViseme;
  renderer: 'sprite' | 'live2d' | 'rive';
  rigAssetId: string | null;
  durationMs: number;
};

type PixiTicker = {
  add(callback: () => void): void;
};

type PixiRenderer = {
  width: number;
  height: number;
  resize(width: number, height: number): void;
};

type PixiStage = {
  addChild(child: unknown): void;
};

type PixiApplication = {
  renderer: PixiRenderer;
  stage: PixiStage;
  ticker: PixiTicker;
  destroy(removeView?: boolean, options?: Record<string, boolean>): void;
};

type Live2DCoreModel = {
  _parameterIds?: unknown[];
  getParameterCount?: () => number;
  getParameterMaximumValue?: (index: number) => number;
  getParameterMinimumValue?: (index: number) => number;
  getParameterIndex?: (id: unknown) => number;
  setParameterValueById?: (id: unknown, value: number, weight?: number) => void;
  setParameterValueByIndex?: (index: number, value: number, weight?: number) => void;
};

type Live2DInternalModel = {
  coreModel?: Live2DCoreModel;
  on?: (event: string, listener: () => void) => unknown;
  off?: (event: string, listener: () => void) => unknown;
  removeListener?: (event: string, listener: () => void) => unknown;
};

type Live2DModel = {
  anchor?: { set(x: number, y?: number): void };
  scale: { set(value: number): void };
  x: number;
  y: number;
  width: number;
  height: number;
  internalModel?: Live2DInternalModel;
  destroy?: (options?: Record<string, boolean>) => void;
};

type PixiGlobal = {
  Application: new (options: Record<string, unknown>) => PixiApplication;
  live2d?: {
    Live2DModel?: {
      from(url: string, options?: Record<string, unknown>): Promise<Live2DModel>;
    };
  };
};

type Live2DWindow = Window & typeof globalThis & {
  PIXI?: PixiGlobal;
  Live2DCubismCore?: unknown;
  __omnixLive2DRendererInstalled?: boolean;
};

const RENDER_EVENT = 'omnix:character-live2d-render';
const RIG_VISEME_EVENT = 'omnix:character-rig-viseme';
const AVATAR_RUNTIME_EVENT = 'omnix:character-avatar-runtime';
const AVATAR_FRAME_EVENT = 'omnix:character-avatar-frame';
const LIVE2D_ZOOM_EVENT = 'omnix:character-live2d-zoom';
const LIVE2D_FRAMING_EVENT = 'omnix:character-live2d-framing';
const RUNTIME_SCRIPTS = [
  '/api/character-live2d/runtime/pixi.min.js',
  '/api/character-live2d/runtime/live2dcubismcore.min.js',
  '/api/character-live2d/runtime/cubism4.min.js',
] as const;
const MODEL_ENTRY_PATHS: Record<string, string> = {
  'character-live2d:open-llm-vtuber-mao-pro': 'runtime/mao_pro.model3.json',
  'character-live2d:open-llm-vtuber-shizuku': 'runtime/shizuku.model3.json',
};
const MOUTH_OPEN_PARAMETER_IDS = ['ParamMouthOpenY', 'PARAM_MOUTH_OPEN_Y', 'ParamA'] as const;
const MOUTH_FORM_PARAMETER_IDS = ['ParamMouthForm', 'PARAM_MOUTH_FORM'] as const;

export const LIVE2D_ZOOM_MIN = 0.75;
export const LIVE2D_ZOOM_MAX = 1.6;
export const LIVE2D_ZOOM_STEP = 0.05;
export type Live2DFraming = 'full' | 'head';

let activeRigAssetId: string | null = null;
let activeHost: HTMLElement | null = null;
let activeApplication: PixiApplication | null = null;
let activeModel: Live2DModel | null = null;
let activeResizeObserver: ResizeObserver | null = null;
let currentMouthShape: Live2DMouthShape = { open: 0, form: 0 };
let silenceTimer: ReturnType<typeof setTimeout> | null = null;
let preciseVisemeUntil = 0;
let currentZoom = 1;
let currentFraming: Live2DFraming = 'full';
let mouthAnimationFrame: number | null = null;
let activeMouthUpdateBinding: { internalModel: Live2DInternalModel; listener: () => void } | null = null;
let activeMouthOpenParameterIndices: number[] = [];
let activeMouthFormParameterIndices: number[] = [];
let renderSequence = 0;
let runtimePromise: Promise<PixiGlobal> | null = null;

export function live2dMouthShapeForViseme(viseme: Live2DViseme): Live2DMouthShape {
  switch (viseme) {
    case 'A': return { open: 1, form: 0.35 };
    case 'O': return { open: 0.78, form: -0.55 };
    case 'E': return { open: 0.58, form: 0.55 };
    case 'L': return { open: 0.52, form: 0.2 };
    case 'other': return { open: 0.5, form: 0 };
    case 'U': return { open: 0.42, form: -0.72 };
    case 'WQ': return { open: 0.3, form: -0.85 };
    case 'FV': return { open: 0.22, form: 0.1 };
    case 'MBP': return { open: 0.03, form: 0 };
    case 'silence':
    default:
      return { open: 0, form: 0 };
  }
}

export function live2dMouthShapeForAvatarFrame(frame: AvatarMouthFrame): Live2DMouthShape {
  switch (frame) {
    case 'small': return { open: 0.28, form: -0.25 };
    case 'medium': return { open: 0.58, form: 0.2 };
    case 'wide': return { open: 0.95, form: 0.05 };
    case 'closed':
    default:
      return { open: 0, form: 0 };
  }
}

export function clampLive2DZoom(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(LIVE2D_ZOOM_MAX, Math.max(LIVE2D_ZOOM_MIN, value));
}

export function live2dZoomPercent(value: number): number {
  return Math.round(clampLive2DZoom(value) * 100);
}

export function readLive2DZoom(): number {
  return currentZoom;
}

export function setLive2DZoom(value: number): void {
  currentZoom = clampLive2DZoom(value);
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LIVE2D_ZOOM_EVENT, { detail: { zoom: currentZoom } }));
}

export function readLive2DFraming(): Live2DFraming {
  return currentFraming;
}

export function setLive2DFraming(value: Live2DFraming): void {
  currentFraming = value === 'head' ? 'head' : 'full';
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LIVE2D_FRAMING_EVENT, { detail: { framing: currentFraming } }));
}

export function live2dModelUrl(rigAssetId: string): string {
  const entryPath = MODEL_ENTRY_PATHS[rigAssetId] ?? 'model.model3.json';
  return `/api/character-live2d/assets/${encodeURIComponent(rigAssetId)}/${entryPath}`;
}

function install(): void {
  if (typeof window === 'undefined') return;
  const liveWindow = window as Live2DWindow;
  if (liveWindow.__omnixLive2DRendererInstalled) return;
  liveWindow.__omnixLive2DRendererInstalled = true;

  window.addEventListener(RENDER_EVENT, (event) => {
    const detail = (event as CustomEvent<Live2DRenderDetail>).detail;
    if (!detail?.host || detail.runtime.avatar_pack?.renderer !== 'live2d') return;
    void renderLive2D(detail.runtime, detail.host);
  });
  window.addEventListener(RIG_VISEME_EVENT, (event) => {
    const detail = (event as CustomEvent<RigVisemeDetail>).detail;
    if (!detail || detail.renderer !== 'live2d' || detail.rigAssetId !== activeRigAssetId) return;
    setViseme(detail.viseme, detail.durationMs);
  });
  window.addEventListener(AVATAR_FRAME_EVENT, (event) => {
    const detail = (event as CustomEvent<{ frame?: AvatarMouthFrame }>).detail;
    if (!detail?.frame || performance.now() < preciseVisemeUntil) return;
    currentMouthShape = live2dMouthShapeForAvatarFrame(detail.frame);
  });
  window.addEventListener(LIVE2D_ZOOM_EVENT, (event) => {
    const zoom = (event as CustomEvent<{ zoom?: number }>).detail?.zoom;
    if (typeof zoom !== 'number') return;
    currentZoom = clampLive2DZoom(zoom);
    fitActiveModel();
  });
  window.addEventListener(LIVE2D_FRAMING_EVENT, (event) => {
    const framing = (event as CustomEvent<{ framing?: Live2DFraming }>).detail?.framing;
    if (framing !== 'full' && framing !== 'head') return;
    currentFraming = framing;
    fitActiveModel();
  });
  window.addEventListener(AVATAR_RUNTIME_EVENT, (event) => {
    const runtime = (event as CustomEvent<CharacterLiveCallRuntime | null>).detail;
    if (runtime?.avatar_pack?.renderer !== 'live2d') destroyActiveRenderer();
  });
}

async function renderLive2D(runtime: CharacterLiveCallRuntime, host: HTMLElement): Promise<void> {
  const pack = runtime.avatar_pack;
  if (!pack?.rig_asset_id || pack.renderer !== 'live2d') return;
  if (activeRigAssetId === pack.rig_asset_id && activeHost === host) return;

  destroyActiveRenderer();
  const sequence = ++renderSequence;
  activeRigAssetId = pack.rig_asset_id;
  activeHost = host;
  host.dataset.renderer = 'live2d';
  host.replaceChildren();

  const canvas = document.createElement('canvas');
  canvas.className = 'assistant-live-character-live2d-canvas';
  canvas.setAttribute('aria-label', `${runtime.display_name} Live2D avatar`);
  const caption = document.createElement('figcaption');
  caption.textContent = `Loading ${runtime.display_name}…`;
  const status = document.createElement('div');
  status.className = 'assistant-live-character-live2d-status';
  status.textContent = 'Loading Live2D runtime…';
  host.append(canvas, status, caption);

  try {
    const pixi = await loadRuntime();
    if (sequence !== renderSequence || activeHost !== host) return;
    const Live2DModelFactory = pixi.live2d?.Live2DModel;
    if (!Live2DModelFactory) throw new Error('Live2D renderer did not initialize.');

    const application = new pixi.Application({
      view: canvas,
      autoStart: true,
      backgroundAlpha: 0,
      antialias: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      autoDensity: true,
    });
    const model = await Live2DModelFactory.from(live2dModelUrl(pack.rig_asset_id), {
      autoInteract: true,
      autoUpdate: true,
    });
    if (sequence !== renderSequence || activeHost !== host) {
      model.destroy?.({ children: true, texture: true, baseTexture: true });
      application.destroy(false, { children: true, texture: true, baseTexture: true });
      return;
    }

    activeApplication = application;
    activeModel = model;
    application.stage.addChild(model);
    bindMouthParameterUpdate(model, sequence);
    activeResizeObserver = new ResizeObserver(() => fitModel(host, application, model));
    activeResizeObserver.observe(host);
    fitModel(host, application, model);
    status.remove();
    updateCaption(host, runtime.display_name, 'ready');
  } catch (error) {
    if (sequence !== renderSequence || activeHost !== host) return;
    status.textContent = error instanceof Error ? error.message : 'Live2D avatar could not be loaded.';
    status.dataset.state = 'error';
    updateCaption(host, runtime.display_name, 'error');
  }
}

function fitModel(host: HTMLElement, application: PixiApplication, model: Live2DModel): void {
  const width = Math.max(240, host.clientWidth || 352);
  const height = Math.max(300, host.clientHeight || 440);
  application.renderer.resize(width, height);

  model.scale.set(1);
  const naturalWidth = Math.max(1, model.width);
  const naturalHeight = Math.max(1, model.height);
  const scale = Math.min((width * 0.92) / naturalWidth, (height * 0.96) / naturalHeight);
  const framingScale = currentFraming === 'head' ? 2.2 : 1;
  const fittedScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  model.scale.set(fittedScale * currentZoom * framingScale);
  model.anchor?.set(0.5, 0.5);
  model.x = width / 2;
  model.y = currentFraming === 'head' ? height * 1.04 : height * 0.52;
}

function setViseme(viseme: Live2DViseme, durationMs: number): void {
  currentMouthShape = live2dMouthShapeForViseme(viseme);
  if (silenceTimer !== null) clearTimeout(silenceTimer);
  const holdMs = Math.max(80, Math.min(500, durationMs + 65));
  preciseVisemeUntil = viseme === 'silence' ? 0 : performance.now() + holdMs;
  if (viseme === 'silence') return;
  silenceTimer = setTimeout(() => {
    currentMouthShape = live2dMouthShapeForViseme('silence');
    preciseVisemeUntil = 0;
    silenceTimer = null;
  }, holdMs);
}

function fitActiveModel(): void {
  if (!activeHost || !activeApplication || !activeModel) return;
  fitModel(activeHost, activeApplication, activeModel);
}

function bindMouthParameterUpdate(model: Live2DModel, sequence: number): void {
  releaseMouthParameterUpdate();
  const internalModel = model.internalModel;
  const coreModel = internalModel?.coreModel;
  activeMouthOpenParameterIndices = resolveLive2DParameterIndices(coreModel, MOUTH_OPEN_PARAMETER_IDS);
  activeMouthFormParameterIndices = resolveLive2DParameterIndices(coreModel, MOUTH_FORM_PARAMETER_IDS);

  const applyBeforeModelUpdate = (): void => {
    if (sequence !== renderSequence || activeModel !== model) return;
    const hostFrame = activeHost?.dataset.mouthFrame as AvatarMouthFrame | undefined;
    if (
      hostFrame
      && (hostFrame === 'closed' || hostFrame === 'small' || hostFrame === 'medium' || hostFrame === 'wide')
      && performance.now() >= preciseVisemeUntil
    ) {
      currentMouthShape = live2dMouthShapeForAvatarFrame(hostFrame);
    }
    applyMouthShape(model, currentMouthShape);
  };

  // Apply after motions, expressions, natural movement and physics, immediately
  // before the Cubism core renders. Earlier writes can be overwritten silently.
  if (internalModel?.on) {
    internalModel.on('beforeModelUpdate', applyBeforeModelUpdate);
    activeMouthUpdateBinding = { internalModel, listener: applyBeforeModelUpdate };
    applyBeforeModelUpdate();
    return;
  }

  // Older runtimes without the internal event emitter keep the RAF fallback.
  if (mouthAnimationFrame !== null) cancelAnimationFrame(mouthAnimationFrame);
  const applyOnAnimationFrame = (): void => {
    if (sequence !== renderSequence || activeModel !== model) {
      mouthAnimationFrame = null;
      return;
    }
    applyMouthShape(model, currentMouthShape);
    mouthAnimationFrame = requestAnimationFrame(applyOnAnimationFrame);
  };
  mouthAnimationFrame = requestAnimationFrame(applyOnAnimationFrame);
}

function releaseMouthParameterUpdate(): void {
  if (activeMouthUpdateBinding) {
    const { internalModel, listener } = activeMouthUpdateBinding;
    if (internalModel.off) internalModel.off('beforeModelUpdate', listener);
    else internalModel.removeListener?.('beforeModelUpdate', listener);
    activeMouthUpdateBinding = null;
  }
  activeMouthOpenParameterIndices = [];
  activeMouthFormParameterIndices = [];
  if (mouthAnimationFrame !== null) cancelAnimationFrame(mouthAnimationFrame);
  mouthAnimationFrame = null;
}

export function resolveLive2DParameterIndices(
  coreModel: Live2DCoreModel | null | undefined,
  parameterIds: readonly string[],
): number[] {
  if (!coreModel) return [];
  const count = coreModel.getParameterCount?.() ?? coreModel._parameterIds?.length ?? 0;
  const resolved = new Set<number>();

  for (const parameterId of parameterIds) {
    const index = coreModel.getParameterIndex?.(parameterId);
    // Cubism returns a synthetic index at or above parameter count for unknown
    // IDs. Those values are writable but never affect the rendered model.
    if (typeof index === 'number' && index >= 0 && index < count) resolved.add(index);
  }

  coreModel._parameterIds?.forEach((parameterId, index) => {
    const readableId = typeof parameterId === 'string'
      ? parameterId
      : typeof (parameterId as { getString?: () => unknown })?.getString === 'function'
        ? String((parameterId as { getString: () => unknown }).getString())
        : String(parameterId);
    if (parameterIds.some((candidate) => candidate.toLocaleLowerCase() === readableId.toLocaleLowerCase())) {
      resolved.add(index);
    }
  });

  return [...resolved];
}

function applyMouthShape(model: Live2DModel, shape: Live2DMouthShape): void {
  const coreModel = model.internalModel?.coreModel;
  if (!coreModel) return;
  if (coreModel.setParameterValueByIndex && activeMouthOpenParameterIndices.length) {
    for (const parameterIndex of activeMouthOpenParameterIndices) {
      const minimum = coreModel.getParameterMinimumValue?.(parameterIndex) ?? 0;
      const maximum = coreModel.getParameterMaximumValue?.(parameterIndex) ?? 1;
      const value = minimum + shape.open * (maximum - minimum);
      coreModel.setParameterValueByIndex(parameterIndex, value, 1);
    }
  } else if (coreModel.setParameterValueById) {
    for (const parameterId of MOUTH_OPEN_PARAMETER_IDS) {
      try { coreModel.setParameterValueById(parameterId, shape.open, 1); } catch { /* legacy runtime fallback */ }
    }
  }
  if (coreModel.setParameterValueByIndex && activeMouthFormParameterIndices.length) {
    for (const parameterIndex of activeMouthFormParameterIndices) {
      coreModel.setParameterValueByIndex(parameterIndex, shape.form, 1);
    }
  } else if (coreModel.setParameterValueById) {
    for (const parameterId of MOUTH_FORM_PARAMETER_IDS) {
      try { coreModel.setParameterValueById(parameterId, shape.form, 1); } catch { /* optional parameter */ }
    }
  }
}

function updateCaption(host: HTMLElement, displayName: string, state: 'ready' | 'error'): void {
  const caption = host.querySelector<HTMLElement>('figcaption');
  if (!caption) return;
  caption.textContent = state === 'error' ? `${displayName} Live2D unavailable` : displayName;
}

function loadRuntime(): Promise<PixiGlobal> {
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    for (const source of RUNTIME_SCRIPTS) await loadScript(source);
    const pixi = (window as Live2DWindow).PIXI;
    if (!pixi?.Application || !pixi.live2d?.Live2DModel) {
      throw new Error('Installed Live2D browser runtime is incomplete.');
    }
    return pixi;
  })().catch((error) => {
    runtimePromise = null;
    throw error;
  });
  return runtimePromise;
}

function loadScript(source: string): Promise<void> {
  const existing = document.querySelector<HTMLScriptElement>(`script[data-omnix-live2d-source="${source}"]`);
  if (existing?.dataset.loaded === 'true') return Promise.resolve();
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`Could not load ${source}`)), { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = source;
    script.async = false;
    script.dataset.omnixLive2dSource = source;
    script.addEventListener('load', () => {
      script.dataset.loaded = 'true';
      resolve();
    }, { once: true });
    script.addEventListener('error', () => reject(new Error(`Could not load ${source}`)), { once: true });
    document.head.append(script);
  });
}

function destroyActiveRenderer(): void {
  renderSequence += 1;
  if (silenceTimer !== null) clearTimeout(silenceTimer);
  silenceTimer = null;
  releaseMouthParameterUpdate();
  preciseVisemeUntil = 0;
  currentMouthShape = { open: 0, form: 0 };
  activeResizeObserver?.disconnect();
  activeResizeObserver = null;
  if (activeApplication) {
    activeApplication.destroy(false, { children: true, texture: true, baseTexture: true });
  } else {
    activeModel?.destroy?.({ children: true, texture: true, baseTexture: true });
  }
  activeModel = null;
  activeApplication = null;
  activeRigAssetId = null;
  activeHost = null;
}

export function isLive2DPack(pack: CharacterAvatarPack | null | undefined): boolean {
  return pack?.renderer === 'live2d' && Boolean(pack.rig_asset_id);
}

install();
