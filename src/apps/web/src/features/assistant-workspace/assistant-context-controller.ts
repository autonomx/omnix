import { DesktopTemporalCapture } from './desktop-temporal-capture';

type ResearchMode = 'disabled' | 'quick' | 'deep';

type DesktopShareSession = {
  stream: MediaStream;
  video: HTMLVideoElement;
  capture: DesktopTemporalCapture;
  sourceFingerprint: string;
};

export type DesktopCompanionCaptureSnapshot = {
  sessionId: string | null;
  characterId: string | null;
  sourceFingerprint: string;
  capture: DesktopTemporalCapture;
};

type AssistantContextWindow = Window & typeof globalThis & {
  __omnixAssistantContextInitialized?: boolean;
};

type DisplayMediaDevices = MediaDevices & {
  getDisplayMedia?: (constraints?: {
    video?: boolean | MediaTrackConstraints;
    audio?: boolean;
  }) => Promise<MediaStream>;
};

const CONTEXT_CONTROLS_ATTRIBUTE = 'data-omnix-context-controls';
const DESKTOP_ACTION_ATTRIBUTE = 'data-omnix-desktop-action';
const DESKTOP_STATUS_ATTRIBUTE = 'data-omnix-desktop-status';
const MESSAGE_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages(\/stream)?$/;
const SESSION_PATH = /^\/api\/chat\/sessions\/([^/]+)$/;
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const DEEP_RESEARCH_PAGES_STORAGE_KEY = 'omnix.deepResearch.maxPages';
const DEFAULT_DEEP_RESEARCH_PAGES = 12;
const MAX_DEEP_RESEARCH_PAGES = 30;
const assistantContextWindow = window as AssistantContextWindow;

let profileDefaultMode: ResearchMode = 'disabled';
let researchMode: ResearchMode = 'disabled';
let deepResearchMaxPages = DEFAULT_DEEP_RESEARCH_PAGES;
let activeSessionId: string | null = null;
let nativeFetch: typeof window.fetch | null = null;
let desktopShare: DesktopShareSession | null = null;
let desktopStatus = 'Off';
const knownResearchModes = new Map<string, ResearchMode>();
const researchModePersistenceQueues = new Map<string, Promise<void>>();

export function initializeAssistantContextController(root: ParentNode = document): void {
  if (assistantContextWindow.__omnixAssistantContextInitialized) return;
  assistantContextWindow.__omnixAssistantContextInitialized = true;
  installFetchInterceptor();
  void loadProfileResearchDefault();
  injectControls(root);
  const observer = new MutationObserver(() => {
    if (assistantContextControlsMissing(root)) injectControls(root);
  });
  const observeTarget = root instanceof Document ? root.documentElement : root;
  observer.observe(observeTarget, { childList: true, subtree: true });
  window.addEventListener('beforeunload', () => stopDesktopShare(), { once: true });
}

export function assistantContextControlsMissing(root: ParentNode = document): boolean {
  const composerActions = root.querySelector<HTMLElement>('.assistant-composer-actions');
  const audioDevices = root.querySelector<HTMLElement>('.assistant-audio-devices');
  const composerControls = root.querySelector<HTMLElement>('.assistant-composer-controls');
  const contextHost = assistantContextHost(composerActions, composerControls);
  const composerMissing = Boolean(contextHost && !contextHost.querySelector(`[${CONTEXT_CONTROLS_ATTRIBUTE}]`));
  const desktopActionMissing = Boolean(
    composerActions && !composerActions.querySelector(`[${DESKTOP_ACTION_ATTRIBUTE}]`),
  );
  const desktopStatusMissing = Boolean(
    audioDevices && !audioDevices.querySelector(`[${DESKTOP_STATUS_ATTRIBUTE}]`),
  );
  return composerMissing || desktopActionMissing || desktopStatusMissing;
}

export function isAssistantMessageRequest(url: string, method: string): boolean {
  const parsed = new URL(url, window.location.origin);
  return method.toUpperCase() === 'POST' && MESSAGE_PATH.test(parsed.pathname);
}

export function enhancedAssistantMessageUrl(url: string): string | null {
  const parsed = new URL(url, window.location.origin);
  const match = parsed.pathname.match(MESSAGE_PATH);
  if (!match) return null;
  parsed.pathname = `/api/assistant/context/chat/sessions/${match[1]}/messages${match[2] ?? ''}`;
  return parsed.toString();
}

export function webResearchModeLabel(mode: ResearchMode): string {
  if (mode === 'quick') return 'Quick search';
  if (mode === 'deep') return 'Deep research';
  return 'Disabled';
}

export function normalizeResearchMode(value: unknown): ResearchMode {
  if (value === 'quick' || value === 'deep' || value === 'disabled') return value;
  return 'disabled';
}

export function normalizeDeepResearchPageLimit(
  value: unknown,
  fallback = DEFAULT_DEEP_RESEARCH_PAGES,
): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  const candidate = Number.isFinite(numeric) ? Math.trunc(numeric) : fallback;
  return Math.max(1, Math.min(MAX_DEEP_RESEARCH_PAGES, candidate));
}

export function desktopStatusLabel(isSharing: boolean, status: string): string {
  return isSharing || status !== 'Off' ? status : 'Off';
}

export function currentDesktopCompanionCapture(): DesktopCompanionCaptureSnapshot | null {
  if (!desktopShare) return null;
  return {
    sessionId: activeSessionId,
    characterId: null,
    sourceFingerprint: desktopShare.sourceFingerprint,
    capture: desktopShare.capture,
  };
}

function installFetchInterceptor(): void {
  const originalFetch = window.fetch.bind(window);
  nativeFetch = originalFetch;
  const wrappedFetch: typeof window.fetch = async (input, init) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const inputUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const parsed = new URL(inputUrl, window.location.origin);
    const sessionMatch = parsed.pathname.match(SESSION_PATH);

    if (method === 'GET' && sessionMatch) {
      const response = await originalFetch(input, init);
      if (response.ok) void applySessionResearchMode(decodePathSegment(sessionMatch[1]), response.clone());
      return response;
    }
    if (!isAssistantMessageRequest(inputUrl, method)) return originalFetch(input, init);

    const messageMatch = parsed.pathname.match(MESSAGE_PATH);
    activeSessionId = messageMatch?.[1] ? decodePathSegment(messageMatch[1]) : null;

    const shouldEnhance = researchMode !== 'disabled' || desktopShare !== null;
    if (!shouldEnhance) {
      const responsePromise = originalFetch(input, init);
      deferResearchModePersistence(responsePromise, activeSessionId, researchMode);
      dispatchPerformance('assistant_context_chat_request_dispatched', {
        sessionId: activeSessionId,
        researchMode,
        enhanced: false,
        persistenceDeferred: true,
      });
      return responsePromise;
    }

    const bodyText = await requestBodyText(input, init);
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(bodyText) as Record<string, unknown>;
    } catch {
      const responsePromise = originalFetch(input, init);
      deferResearchModePersistence(responsePromise, activeSessionId, researchMode);
      return responsePromise;
    }

    let desktopPayload: Awaited<ReturnType<DesktopTemporalCapture['buildPayload']>> | undefined;
    if (desktopShare) {
      try {
        desktopPayload = await desktopShare.capture.buildPayload();
        desktopStatus = desktopPayload.captureMode === 'temporal'
          ? `${desktopPayload.selectedHistoryFrames} history + current`
          : 'Current frame attached';
      } catch (error) {
        desktopStatus = error instanceof Error ? error.message : 'Capture failed';
        stopDesktopShare({ resetStatus: false });
      }
      renderControls();
    }

    const enhancedUrl = enhancedAssistantMessageUrl(inputUrl);
    if (!enhancedUrl) {
      const responsePromise = originalFetch(input, init);
      deferResearchModePersistence(responsePromise, activeSessionId, researchMode);
      return responsePromise;
    }
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set('Content-Type', 'application/json');
    dispatchPerformance('assistant_context_chat_request_dispatched', {
      sessionId: activeSessionId,
      researchMode,
      enhanced: true,
      persistenceDeferred: true,
    });
    const enhancedResponse = await originalFetch(enhancedUrl, {
      ...init,
      method: 'POST',
      headers,
      body: JSON.stringify({
        ...payload,
        web_research_mode: researchMode,
        deep_research_max_pages: researchMode === 'deep' ? deepResearchMaxPages : undefined,
        desktop_current_image_data_url: desktopPayload?.currentImageDataUrl,
        desktop_history_image_data_url: desktopPayload?.historyImageDataUrl,
        desktop_combined_image_data_url: desktopPayload?.combinedImageDataUrl,
        desktop_history_timestamps: desktopPayload?.historyTimestamps ?? [],
        desktop_capture_mode: desktopPayload?.captureMode ?? 'single',
      }),
    });
    if (enhancedResponse.status === 404) {
      const fallbackPromise = originalFetch(input, init);
      deferResearchModePersistence(fallbackPromise, activeSessionId, researchMode);
      return fallbackPromise;
    }
    deferResearchModePersistence(Promise.resolve(enhancedResponse), activeSessionId, researchMode);
    return enhancedResponse;
  };
  window.fetch = wrappedFetch;
}

async function applySessionResearchMode(sessionId: string, response: Response): Promise<void> {
  try {
    const session = await response.json() as { research_mode_override?: unknown };
    activeSessionId = sessionId;
    researchMode = session.research_mode_override == null
      ? profileDefaultMode
      : normalizeResearchMode(session.research_mode_override);
    knownResearchModes.set(sessionId, researchMode);
    renderControls();
  } catch {
    // Session reads remain usable when research metadata is absent.
  }
}

async function loadProfileResearchDefault(): Promise<void> {
  const fetchImpl = nativeFetch ?? window.fetch.bind(window);
  try {
    const response = await fetchImpl('/api/settings');
    if (!response.ok) return;
    const payload = await response.json() as Record<string, unknown>;
    const settings = asRecord(payload.settings);
    const profile = asRecord(settings.settings_control_center);
    const assistant = asRecord(profile.assistant);
    profileDefaultMode = normalizeResearchMode(assistant.researchDefaultMode);
    const persistedPageLimit = readStoredDeepResearchPageLimit();
    deepResearchMaxPages = normalizeDeepResearchPageLimit(
      persistedPageLimit ?? assistant.researchMaxSources,
      deepResearchMaxPages,
    );
    if (!activeSessionId) researchMode = profileDefaultMode;
    renderControls();
  } catch {
    // Settings availability must not block chat.
  }
}

function deferResearchModePersistence(
  responsePromise: Promise<Response>,
  sessionId: string | null,
  mode: ResearchMode,
): void {
  if (!sessionId || knownResearchModes.get(sessionId) === mode) return;
  void responsePromise.then(
    () => scheduleConversationResearchModePersistence(sessionId, mode),
    () => scheduleConversationResearchModePersistence(sessionId, mode),
  );
}

function scheduleConversationResearchModePersistence(sessionId: string, mode: ResearchMode): void {
  if (knownResearchModes.get(sessionId) === mode) return;
  const previous = researchModePersistenceQueues.get(sessionId) ?? Promise.resolve();
  const next = previous
    .catch(() => undefined)
    .then(async () => {
      if (knownResearchModes.get(sessionId) === mode) return;
      const persisted = await persistConversationResearchMode(sessionId, mode);
      if (persisted) {
        knownResearchModes.set(sessionId, mode);
        dispatchPerformance('assistant_context_research_mode_persisted', {
          sessionId,
          researchMode: mode,
        });
      }
    });
  researchModePersistenceQueues.set(sessionId, next);
  const cleanup = (): void => {
    if (researchModePersistenceQueues.get(sessionId) === next) {
      researchModePersistenceQueues.delete(sessionId);
    }
  };
  void next.then(cleanup, cleanup);
}

async function persistConversationResearchMode(sessionId: string, mode: ResearchMode): Promise<boolean> {
  const fetchImpl = nativeFetch;
  if (!fetchImpl) return false;
  try {
    const response = await fetchImpl(`/api/chat/sessions/${encodeURIComponent(sessionId)}/research-mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ research_mode_override: mode }),
    });
    return response.ok;
  } catch {
    // The selected turn still carries its explicit mode if session persistence is unavailable.
    return false;
  }
}

async function requestBodyText(input: RequestInfo | URL, init?: RequestInit): Promise<string> {
  if (typeof init?.body === 'string') return init.body;
  if (input instanceof Request) return input.clone().text();
  return '';
}

function injectControls(root: ParentNode): void {
  const composerActions = root.querySelector<HTMLElement>('.assistant-composer-actions');
  const composerControls = root.querySelector<HTMLElement>('.assistant-composer-controls');
  const contextHost = assistantContextHost(composerActions, composerControls);
  if (contextHost && !contextHost.querySelector(`[${CONTEXT_CONTROLS_ATTRIBUTE}]`)) {
    const container = document.createElement('div');
    container.className = 'assistant-context-controls';
    container.setAttribute(CONTEXT_CONTROLS_ATTRIBUTE, 'true');

    const webLabel = document.createElement('label');
    webLabel.className = 'assistant-context-mode';
    const webCaption = document.createElement('span');
    webCaption.textContent = 'Web research';
    const webSelect = document.createElement('select');
    webSelect.setAttribute('aria-label', 'Web research mode');
    for (const mode of ['disabled', 'quick', 'deep'] as const) {
      const option = document.createElement('option');
      option.value = mode;
      option.textContent = webResearchModeLabel(mode);
      webSelect.append(option);
    }
    webSelect.value = researchMode;
    webSelect.addEventListener('change', () => {
      researchMode = normalizeResearchMode(webSelect.value);
      if (activeSessionId) scheduleConversationResearchModePersistence(activeSessionId, researchMode);
      renderControls();
    });
    webLabel.append(webCaption, webSelect);

    const pageBudget = document.createElement('label');
    pageBudget.className = 'assistant-context-page-budget';
    pageBudget.setAttribute('data-omnix-deep-research-pages', 'true');
    const pageCaption = document.createElement('span');
    pageCaption.textContent = 'Max pages';
    const pageInput = document.createElement('input');
    pageInput.type = 'number';
    pageInput.min = '1';
    pageInput.max = String(MAX_DEEP_RESEARCH_PAGES);
    pageInput.step = '1';
    pageInput.inputMode = 'numeric';
    pageInput.setAttribute('aria-label', 'Maximum pages to search');
    pageInput.value = String(deepResearchMaxPages);
    pageInput.addEventListener('change', () => {
      deepResearchMaxPages = normalizeDeepResearchPageLimit(pageInput.value, deepResearchMaxPages);
      pageInput.value = String(deepResearchMaxPages);
      storeDeepResearchPageLimit(deepResearchMaxPages);
      renderControls();
    });
    pageBudget.append(pageCaption, pageInput);

    container.append(webLabel, pageBudget);
    contextHost.append(container);
  }

  if (composerActions && !composerActions.querySelector(`[${DESKTOP_ACTION_ATTRIBUTE}]`)) {
    const desktopAction = document.createElement('button');
    desktopAction.type = 'button';
    desktopAction.className = 'assistant-context-desktop-inline assistant-context-desktop';
    desktopAction.setAttribute(DESKTOP_ACTION_ATTRIBUTE, 'true');
    desktopAction.addEventListener('click', () => void toggleDesktopShare());
    composerActions.prepend(desktopAction);
  }

  const audioDevices = root.querySelector<HTMLElement>('.assistant-audio-devices');
  if (audioDevices && !audioDevices.querySelector(`[${DESKTOP_STATUS_ATTRIBUTE}]`)) {
    const row = document.createElement('div');
    row.setAttribute(DESKTOP_STATUS_ATTRIBUTE, 'true');
    const label = document.createElement('span');
    label.textContent = 'Desktop';
    const value = document.createElement('strong');
    value.className = 'assistant-desktop-status-value';
    const indicator = document.createElement('i');
    indicator.setAttribute('aria-hidden', 'true');
    row.append(label, value, indicator);
    audioDevices.append(row);
  }
  renderControls();
}

function assistantContextHost(
  composerActions: HTMLElement | null,
  composerControls: HTMLElement | null,
): HTMLElement | null {
  return composerActions?.closest<HTMLElement>('.assistant-composer') ?? composerControls;
}

function renderControls(): void {
  document.querySelectorAll<HTMLSelectElement>('select[aria-label="Web research mode"]').forEach((select) => {
    select.value = researchMode;
  });
  document.querySelectorAll<HTMLElement>('[data-omnix-deep-research-pages]').forEach((element) => {
    element.hidden = researchMode !== 'deep';
  });
  document.querySelectorAll<HTMLInputElement>('input[aria-label="Maximum pages to search"]').forEach((input) => {
    input.value = String(deepResearchMaxPages);
  });
  document.querySelectorAll<HTMLButtonElement>('.assistant-context-desktop').forEach((button) => {
    const active = desktopShare !== null;
    button.classList.toggle('active', active);
    button.setAttribute('aria-label', active ? 'Stop desktop sharing' : 'Start desktop sharing');
    button.innerHTML = `<span>Desktop</span><strong>${active ? 'Sharing' : 'Off'}</strong>`;
  });
  document.querySelectorAll<HTMLElement>('.assistant-desktop-status-value').forEach((element) => {
    element.textContent = desktopStatusLabel(desktopShare !== null, desktopStatus);
  });
}

function decodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

async function toggleDesktopShare(): Promise<void> {
  if (desktopShare) {
    stopDesktopShare();
    renderControls();
    return;
  }
  const mediaDevices = navigator.mediaDevices as DisplayMediaDevices | undefined;
  if (!mediaDevices?.getDisplayMedia) {
    desktopStatus = 'Screen capture unavailable';
    renderControls();
    return;
  }
  try {
    desktopStatus = 'Choose a screen or window';
    renderControls();
    const stream = await mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 5, max: 10 } },
      audio: false,
    });
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream;
    await video.play();
    await waitForVideoDimensions(video);
    const capture = new DesktopTemporalCapture(video);
    capture.start();
    desktopShare = {
      stream,
      video,
      capture,
      sourceFingerprint: desktopSourceFingerprint(stream),
    };
    desktopStatus = 'Buffering recent frames';
    window.dispatchEvent(new CustomEvent('omnix:desktop-share-changed', { detail: { sharing: true } }));
    stream.getVideoTracks()[0]?.addEventListener('ended', () => {
      stopDesktopShare();
      renderControls();
    }, { once: true });
  } catch (error) {
    desktopStatus = error instanceof Error && error.name === 'NotAllowedError'
      ? 'Sharing cancelled'
      : error instanceof Error ? error.message : 'Could not share desktop';
    stopDesktopShare({ resetStatus: false });
  }
  renderControls();
}

function stopDesktopShare(options: { resetStatus?: boolean } = {}): void {
  const current = desktopShare;
  desktopShare = null;
  current?.capture.stop();
  current?.stream.getTracks().forEach((track) => track.stop());
  if (current) current.video.srcObject = null;
  if (options.resetStatus !== false) desktopStatus = 'Off';
  if (current) window.dispatchEvent(new CustomEvent('omnix:desktop-share-changed', { detail: { sharing: false } }));
}

function desktopSourceFingerprint(stream: MediaStream): string {
  const track = stream.getVideoTracks()[0];
  const settings = track?.getSettings() as MediaTrackSettings & { displaySurface?: string };
  const source = `${settings.displaySurface ?? 'unknown'}:${track?.label ?? 'desktop'}`;
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `desktop-source:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

function waitForVideoDimensions(video: HTMLVideoElement): Promise<void> {
  if (video.videoWidth > 0 && video.videoHeight > 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => reject(new Error('Desktop preview did not become ready')), 5_000);
    video.addEventListener('loadedmetadata', () => {
      window.clearTimeout(timeoutId);
      resolve();
    }, { once: true });
  });
}

function dispatchPerformance(stage: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function readStoredDeepResearchPageLimit(): number | null {
  try {
    const value = window.localStorage.getItem(DEEP_RESEARCH_PAGES_STORAGE_KEY);
    return value === null ? null : normalizeDeepResearchPageLimit(value);
  } catch {
    return null;
  }
}

function storeDeepResearchPageLimit(value: number): void {
  try {
    window.localStorage.setItem(DEEP_RESEARCH_PAGES_STORAGE_KEY, String(value));
  } catch {
    // Storage is optional; the chosen limit remains active for this page.
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initializeAssistantContextController(), { once: true });
} else {
  initializeAssistantContextController();
}
