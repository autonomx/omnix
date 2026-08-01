import type { CharacterAvatarPack, CharacterLiveCallRuntime } from './characterClient';

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
  setParameterValueById?: (id: string, value: number, weight?: number) => void;
};

type Live2DModel = {
  anchor?: { set(x: number, y?: number): void };
  scale: { set(value: number): void };
  x: number;
  y: number;
  width: number;
  height: number;
  internalModel?: { coreModel?: Live2DCoreModel };
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
const RUNTIME_SCRIPTS = [
  '/api/character-live2d/runtime/pixi.min.js',
  '/api/character-live2d/runtime/live2dcubismcore.min.js',
  '/api/character-live2d/runtime/cubism4.min.js',
] as const;
const MOUTH_OPEN_PARAMETER_IDS = ['ParamMouthOpenY', 'PARAM_MOUTH_OPEN_Y', 'ParamA'] as const;
const MOUTH_FORM_PARAMETER_IDS = ['ParamMouthForm', 'PARAM_MOUTH_FORM'] as const;

let activeRigAssetId: string | null = null;
let activeHost: HTMLElement | null = null;
let activeApplication: PixiApplication | null = null;
let activeModel: Live2DModel | null = null;
let activeResizeObserver: ResizeObserver | null = null;
let currentMouthShape: Live2DMouthShape = { open: 0, form: 0 };
let silenceTimer: number | null = null;
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

export function live2dModelUrl(rigAssetId: string): string {
  return `/api/character-live2d/assets/${encodeURIComponent(rigAssetId)}/model.model3.json`;
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
}

async function renderLive2D(runtime: CharacterLiveCallRuntime, host: HTMLElement): Promise<void> {
  const pack = runtime.avatar_pack;
  if (!pack?.rig_asset_id || pack.renderer !== 'live2d') return;
  if (activeRigAssetId === pack.rig_asset_id && activeHost === host && activeModel) return;

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
    application.ticker.add(() => applyMouthShape(model, currentMouthShape));
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
  model.scale.set(Number.isFinite(scale) && scale > 0 ? scale : 1);
  model.anchor?.set(0.5, 0.5);
  model.x = width / 2;
  model.y = height * 0.52;
}

function setViseme(viseme: Live2DViseme, durationMs: number): void {
  currentMouthShape = live2dMouthShapeForViseme(viseme);
  if (silenceTimer !== null) window.clearTimeout(silenceTimer);
  if (viseme === 'silence') return;
  silenceTimer = window.setTimeout(() => {
    currentMouthShape = live2dMouthShapeForViseme('silence');
    silenceTimer = null;
  }, Math.max(80, Math.min(500, durationMs + 65)));
}

function applyMouthShape(model: Live2DModel, shape: Live2DMouthShape): void {
  const coreModel = model.internalModel?.coreModel;
  if (!coreModel?.setParameterValueById) return;
  for (const parameterId of MOUTH_OPEN_PARAMETER_IDS) {
    try { coreModel.setParameterValueById(parameterId, shape.open, 1); } catch { /* model may not expose this alias */ }
  }
  for (const parameterId of MOUTH_FORM_PARAMETER_IDS) {
    try { coreModel.setParameterValueById(parameterId, shape.form, 1); } catch { /* optional parameter */ }
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
  if (silenceTimer !== null) window.clearTimeout(silenceTimer);
  silenceTimer = null;
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
