type ResearchMode = 'disabled' | 'quick' | 'deep';

type ReleaseAvailability = {
  disabled: boolean;
  quick: boolean;
  deep: boolean;
  hermes_planner: boolean;
};

type ResearchStatusPayload = {
  release?: {
    master_enabled?: boolean;
    quick_percentage?: number;
    deep_local_percentage?: number;
    hermes_percentage?: number;
    availability?: Partial<ReleaseAvailability>;
  };
};

type ResearchUnavailableDetail = {
  code?: string;
  requested_mode?: string;
  reason?: string;
  available_modes?: string[];
  downgrade_available?: boolean;
};

type ReleaseWindow = Window & typeof globalThis & {
  __omnixResearchReleaseInitialized?: boolean;
};

const CONTROLS_ATTRIBUTE = 'data-omnix-context-controls';
const RELEASE_ATTRIBUTE = 'data-omnix-research-release';
const MESSAGE_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages(\/stream)?$/;
const ENHANCED_MESSAGE_PATH = /^\/api\/assistant\/context\/chat\/sessions\/([^/]+)\/messages(\/stream)?$/;
const SESSION_PATH = /^\/api\/chat\/sessions\/([^/]+)$/;
const releaseWindow = window as ReleaseWindow;

let allowDowngrade = false;
let activeSessionId: string | null = null;
let availability: ReleaseAvailability = { disabled: true, quick: true, deep: true, hermes_planner: false };
let releaseMessage = 'Research availability is loading.';
let baseFetch: typeof window.fetch | null = null;

export function initializeResearchReleaseController(root: ParentNode = document): void {
  if (releaseWindow.__omnixResearchReleaseInitialized) return;
  releaseWindow.__omnixResearchReleaseInitialized = true;
  installFetchWrapper();
  injectReleaseControls(root);
  void loadReleaseStatus();
  const observer = new MutationObserver(() => injectReleaseControls(root));
  const target = root instanceof Document ? root.documentElement : root;
  observer.observe(target, { childList: true, subtree: true });
}

export function shouldOfferResearchDowngrade(mode: ResearchMode, current: ReleaseAvailability): boolean {
  return mode === 'deep' && !current.deep && current.quick;
}

export function addResearchDowngradeConsent(
  payload: Record<string, unknown>,
  consent: boolean,
): Record<string, unknown> {
  return { ...payload, allow_research_downgrade: consent };
}

export function researchReleaseMessage(detail: ResearchUnavailableDetail): string {
  const reason = humanize(detail.reason || 'research mode unavailable');
  if (detail.downgrade_available) return `${reason}. Quick Search is available when fallback is explicitly allowed.`;
  const available = detail.available_modes?.length ? ` Available: ${detail.available_modes.join(', ')}.` : '';
  return `${reason}.${available}`;
}

function installFetchWrapper(): void {
  const originalFetch = window.fetch.bind(window);
  baseFetch = originalFetch;
  window.fetch = async (input, init) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const inputUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const parsed = new URL(inputUrl, window.location.origin);
    const sessionMatch = parsed.pathname.match(SESSION_PATH);
    if (method === 'GET' && sessionMatch) {
      const response = await originalFetch(input, init);
      if (response.ok) {
        activeSessionId = sessionMatch[1] ? decodePathSegment(sessionMatch[1]) : null;
        void loadReleaseStatus(activeSessionId);
      }
      return response;
    }

    const messageMatch = parsed.pathname.match(MESSAGE_PATH) ?? parsed.pathname.match(ENHANCED_MESSAGE_PATH);
    if (method !== 'POST' || !messageMatch) return originalFetch(input, init);
    activeSessionId = messageMatch[1] ? decodePathSegment(messageMatch[1]) : activeSessionId;
    const body = await requestBodyText(input, init);
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(body) as Record<string, unknown>;
    } catch {
      return originalFetch(input, init);
    }
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set('Content-Type', 'application/json');
    const response = await originalFetch(input, {
      ...init,
      method: 'POST',
      headers,
      body: JSON.stringify(addResearchDowngradeConsent(payload, allowDowngrade)),
    });
    if (response.status === 409) void showUnavailableResponse(response.clone());
    else if (response.ok) releaseMessage = 'Research mode accepted for this turn.';
    renderReleaseControls();
    return response;
  };
}

async function loadReleaseStatus(sessionId: string | null = activeSessionId): Promise<void> {
  const fetcher = baseFetch ?? window.fetch.bind(window);
  try {
    const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
    const response = await fetcher(`/api/assistant/research/status${query}`);
    if (!response.ok) throw new Error('Research availability could not be loaded.');
    const payload = await response.json() as ResearchStatusPayload;
    availability = {
      disabled: payload.release?.availability?.disabled !== false,
      quick: payload.release?.availability?.quick !== false,
      deep: payload.release?.availability?.deep === true,
      hermes_planner: payload.release?.availability?.hermes_planner === true,
    };
    releaseMessage = releaseSummary(payload, availability);
  } catch (error) {
    releaseMessage = error instanceof Error ? error.message : 'Research availability is unavailable.';
  }
  renderReleaseControls();
}

async function showUnavailableResponse(response: Response): Promise<void> {
  try {
    const payload = await response.json() as { detail?: ResearchUnavailableDetail };
    releaseMessage = researchReleaseMessage(payload.detail ?? {});
  } catch {
    releaseMessage = 'The selected research mode is unavailable.';
  }
  renderReleaseControls();
}

function injectReleaseControls(root: ParentNode): void {
  const container = root.querySelector<HTMLElement>(`.assistant-composer > [${CONTROLS_ATTRIBUTE}]`)
    ?? root.querySelector<HTMLElement>(`[${CONTROLS_ATTRIBUTE}]`);
  if (!container || container.querySelector(`[${RELEASE_ATTRIBUTE}]`)) {
    renderReleaseControls();
    return;
  }
  const release = document.createElement('div');
  release.className = 'assistant-research-release-controls';
  release.setAttribute(RELEASE_ATTRIBUTE, 'true');
  const fallback = document.createElement('label');
  fallback.className = 'assistant-research-fallback';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.setAttribute('aria-label', 'Allow Quick Search fallback');
  checkbox.checked = allowDowngrade;
  checkbox.addEventListener('change', () => {
    allowDowngrade = checkbox.checked;
    renderReleaseControls();
  });
  const fallbackText = document.createElement('span');
  fallbackText.textContent = 'Allow Quick fallback';
  fallback.append(checkbox, fallbackText);
  const status = document.createElement('small');
  status.className = 'assistant-research-release-status';
  status.setAttribute('role', 'status');
  release.append(fallback, status);
  container.append(release);

  const select = container.querySelector<HTMLSelectElement>('select[aria-label="Web research mode"]');
  if (select && !select.dataset.releaseListener) {
    select.dataset.releaseListener = 'true';
    select.addEventListener('change', renderReleaseControls);
  }
  renderReleaseControls();
}

function renderReleaseControls(): void {
  const select = visibleResearchModeSelect();
  if (select) {
    const quickOption = select.querySelector<HTMLOptionElement>('option[value="quick"]');
    const deepOption = select.querySelector<HTMLOptionElement>('option[value="deep"]');
    if (quickOption) {
      setBooleanProperty(quickOption, 'disabled', !availability.quick);
      setText(quickOption, availability.quick ? 'Quick search' : 'Quick search · unavailable');
    }
    if (deepOption) {
      setBooleanProperty(deepOption, 'disabled', !availability.deep);
      setText(deepOption, availability.deep ? 'Deep research' : 'Deep research · unavailable');
    }
  }
  const mode = (select?.value ?? 'disabled') as ResearchMode;
  document.querySelectorAll<HTMLElement>('.assistant-research-fallback').forEach((element) => {
    const show = shouldOfferResearchDowngrade(mode, availability);
    setBooleanProperty(element, 'hidden', !show);
  });
  document.querySelectorAll<HTMLInputElement>('input[aria-label="Allow Quick Search fallback"]').forEach((input) => {
    setBooleanProperty(input, 'checked', allowDowngrade);
  });
  document.querySelectorAll<HTMLElement>('.assistant-research-release-status').forEach((element) => {
    setText(element, releaseMessage);
  });
}

function visibleResearchModeSelect(): HTMLSelectElement | null {
  return document.querySelector<HTMLSelectElement>('.assistant-composer > [data-omnix-context-controls] select[aria-label="Web research mode"]')
    ?? document.querySelector<HTMLSelectElement>('select[aria-label="Web research mode"]');
}

function setText(element: Element, value: string): void {
  if (element.textContent !== value) element.textContent = value;
}

function setBooleanProperty<TElement extends Element, TKey extends keyof TElement>(
  element: TElement,
  key: TKey,
  value: boolean,
): void {
  if (element[key] !== value) element[key] = value as TElement[TKey];
}

function releaseSummary(payload: ResearchStatusPayload, current: ReleaseAvailability): string {
  if (payload.release?.master_enabled === false) return 'Research rollback is active.';
  if (current.deep) return current.hermes_planner ? 'Deep Research and Hermes planning are available.' : 'Deep Research is available with the local planner.';
  if (current.quick) return 'Quick Search is available. Deep Research is not released for this session.';
  return 'External research is unavailable for this session.';
}

async function requestBodyText(input: RequestInfo | URL, init?: RequestInit): Promise<string> {
  if (typeof init?.body === 'string') return init.body;
  if (input instanceof Request) return input.clone().text();
  return '';
}

function humanize(value: string): string {
  const text = value.replaceAll('_', ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Research mode unavailable';
}

function decodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initializeResearchReleaseController(), { once: true });
} else {
  initializeResearchReleaseController();
}
