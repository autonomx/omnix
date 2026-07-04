import { DesktopTemporalCapture } from './desktop-temporal-capture';

type WebSearchMode = 'automatic' | 'manual' | 'disabled';

type DesktopShareSession = {
  stream: MediaStream;
  video: HTMLVideoElement;
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

const CONTEXT_STORAGE_KEY = 'omnix.chatbot.contextSettings';
const CONTEXT_CONTROLS_ATTRIBUTE = 'data-omnix-context-controls';
const MESSAGE_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages$/;
const assistantContextWindow = window as AssistantContextWindow;

let webSearchMode: WebSearchMode = loadWebSearchMode();
let manualSearchRequested = false;
let desktopShare: DesktopShareSession | null = null;
let desktopStatus = 'Off';

export function initializeAssistantContextController(root: ParentNode = document): void {
  if (assistantContextWindow.__omnixAssistantContextInitialized) return;
  assistantContextWindow.__omnixAssistantContextInitialized = true;
  installFetchInterceptor();
  injectControls(root);
  const observer = new MutationObserver(() => injectControls(root));
  observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('beforeunload', () => stopDesktopShare(), { once: true });
}

export function isAssistantMessageRequest(url: string, method: string): boolean {
  const parsed = new URL(url, window.location.origin);
  return method.toUpperCase() === 'POST' && MESSAGE_PATH.test(parsed.pathname);
}

export function enhancedAssistantMessageUrl(url: string): string | null {
  const parsed = new URL(url, window.location.origin);
  const match = parsed.pathname.match(MESSAGE_PATH);
  if (!match) return null;
  parsed.pathname = `/api/assistant/context/chat/sessions/${match[1]}/messages`;
  return parsed.toString();
}

export function webSearchModeLabel(mode: WebSearchMode, requested = false): string {
  if (mode === 'automatic') return 'Automatic';
  if (mode === 'manual') return requested ? 'Next turn armed' : 'Manual';
  return 'Disabled';
}

function installFetchInterceptor(): void {
  const originalFetch = window.fetch.bind(window);
  const wrappedFetch: typeof window.fetch = async (input, init) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const inputUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    if (!isAssistantMessageRequest(inputUrl, method)) return originalFetch(input, init);

    const shouldEnhance = webSearchMode === 'automatic'
      || (webSearchMode === 'manual' && manualSearchRequested)
      || desktopShare !== null;
    if (!shouldEnhance) return originalFetch(input, init);

    const bodyText = await requestBodyText(input, init);
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(bodyText) as Record<string, unknown>;
    } catch {
      return originalFetch(input, init);
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
        stopDesktopShare();
      }
      renderControls();
    }

    const enhancedUrl = enhancedAssistantMessageUrl(inputUrl);
    if (!enhancedUrl) return originalFetch(input, init);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set('Content-Type', 'application/json');
    const enhancedResponse = await originalFetch(enhancedUrl, {
      ...init,
      method: 'POST',
      headers,
      body: JSON.stringify({
        ...payload,
        web_search_mode: webSearchMode,
        web_search_requested: webSearchMode === 'manual' && manualSearchRequested,
        desktop_current_image_data_url: desktopPayload?.currentImageDataUrl,
        desktop_history_image_data_url: desktopPayload?.historyImageDataUrl,
        desktop_combined_image_data_url: desktopPayload?.combinedImageDataUrl,
        desktop_history_timestamps: desktopPayload?.historyTimestamps ?? [],
        desktop_capture_mode: desktopPayload?.captureMode ?? 'single',
      }),
    });
    if (enhancedResponse.status === 404) return originalFetch(input, init);
    if (enhancedResponse.ok && webSearchMode === 'manual') {
      manualSearchRequested = false;
      renderControls();
    }
    return enhancedResponse;
  };
  window.fetch = wrappedFetch;
}

async function requestBodyText(input: RequestInfo | URL, init?: RequestInit): Promise<string> {
  if (typeof init?.body === 'string') return init.body;
  if (input instanceof Request) return input.clone().text();
  return '';
}

function injectControls(root: ParentNode): void {
  const composerControls = root.querySelector<HTMLElement>('.assistant-composer-controls');
  if (composerControls && !composerControls.querySelector(`[${CONTEXT_CONTROLS_ATTRIBUTE}]`)) {
    const container = document.createElement('div');
    container.className = 'assistant-context-controls';
    container.setAttribute(CONTEXT_CONTROLS_ATTRIBUTE, 'true');

    const webLabel = document.createElement('label');
    webLabel.className = 'assistant-context-mode';
    const webCaption = document.createElement('span');
    webCaption.textContent = 'Web search';
    const webSelect = document.createElement('select');
    webSelect.setAttribute('aria-label', 'Web search mode');
    for (const mode of ['automatic', 'manual', 'disabled'] as const) {
      const option = document.createElement('option');
      option.value = mode;
      option.textContent = mode[0].toUpperCase() + mode.slice(1);
      webSelect.append(option);
    }
    webSelect.value = webSearchMode;
    webSelect.addEventListener('change', () => {
      webSearchMode = isWebSearchMode(webSelect.value) ? webSelect.value : 'disabled';
      manualSearchRequested = false;
      saveWebSearchMode(webSearchMode);
      renderControls();
    });
    webLabel.append(webCaption, webSelect);

    const manualButton = document.createElement('button');
    manualButton.type = 'button';
    manualButton.className = 'assistant-composer-chip assistant-context-manual';
    manualButton.setAttribute('aria-label', 'Search the web for the next message');
    manualButton.addEventListener('click', () => {
      manualSearchRequested = !manualSearchRequested;
      renderControls();
    });

    const desktopButton = document.createElement('button');
    desktopButton.type = 'button';
    desktopButton.className = 'assistant-composer-chip assistant-context-desktop';
    desktopButton.addEventListener('click', () => void toggleDesktopShare());

    container.append(webLabel, manualButton, desktopButton);
    composerControls.append(container);
  }

  const audioDevices = root.querySelector<HTMLElement>('.assistant-audio-devices');
  if (audioDevices && !audioDevices.querySelector('[data-omnix-desktop-status]')) {
    const row = document.createElement('div');
    row.setAttribute('data-omnix-desktop-status', 'true');
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

function renderControls(): void {
  document.querySelectorAll<HTMLSelectElement>('select[aria-label="Web search mode"]').forEach((select) => {
    select.value = webSearchMode;
  });
  document.querySelectorAll<HTMLButtonElement>('.assistant-context-manual').forEach((button) => {
    button.hidden = webSearchMode !== 'manual';
    button.classList.toggle('active', manualSearchRequested);
    button.innerHTML = `<span>Web</span><strong>${webSearchModeLabel(webSearchMode, manualSearchRequested)}</strong>`;
  });
  document.querySelectorAll<HTMLButtonElement>('.assistant-context-desktop').forEach((button) => {
    const active = desktopShare !== null;
    button.classList.toggle('active', active);
    button.setAttribute('aria-label', active ? 'Stop desktop sharing' : 'Start desktop sharing');
    button.innerHTML = `<span>Desktop</span><strong>${active ? 'Sharing' : 'Off'}</strong>`;
  });
  document.querySelectorAll<HTMLElement>('.assistant-desktop-status-value').forEach((element) => {
    element.textContent = desktopShare ? desktopStatus : 'Off';
  });
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
    desktopShare = { stream, video, capture };
    desktopStatus = 'Buffering recent frames';
    stream.getVideoTracks()[0]?.addEventListener('ended', () => {
      stopDesktopShare();
      renderControls();
    }, { once: true });
  } catch (error) {
    desktopStatus = error instanceof Error && error.name === 'NotAllowedError'
      ? 'Sharing cancelled'
      : error instanceof Error ? error.message : 'Could not share desktop';
    stopDesktopShare();
  }
  renderControls();
}

function stopDesktopShare(): void {
  const current = desktopShare;
  desktopShare = null;
  current?.capture.stop();
  current?.stream.getTracks().forEach((track) => track.stop());
  if (current) current.video.srcObject = null;
  desktopStatus = 'Off';
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

function loadWebSearchMode(): WebSearchMode {
  try {
    const raw = window.localStorage.getItem(CONTEXT_STORAGE_KEY);
    if (!raw) return 'disabled';
    const parsed = JSON.parse(raw) as { webSearchMode?: unknown };
    return isWebSearchMode(parsed.webSearchMode) ? parsed.webSearchMode : 'disabled';
  } catch {
    return 'disabled';
  }
}

function saveWebSearchMode(mode: WebSearchMode): void {
  try {
    window.localStorage.setItem(CONTEXT_STORAGE_KEY, JSON.stringify({ webSearchMode: mode }));
  } catch {
    // Storage is optional; the active page still keeps the selected mode.
  }
}

function isWebSearchMode(value: unknown): value is WebSearchMode {
  return value === 'automatic' || value === 'manual' || value === 'disabled';
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initializeAssistantContextController(), { once: true });
} else {
  initializeAssistantContextController();
}
