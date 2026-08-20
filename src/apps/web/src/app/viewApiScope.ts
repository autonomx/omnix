import type { OmnixModuleId } from './modules';

const VIEW_API_FIREWALL_KEY = '__omnixViewApiFirewallInstalled';
const OUTER_VIEW_API_FIREWALL_KEY = '__omnixOuterViewApiFirewallInstalled';
let previousFetch: typeof window.fetch | null = null;
let previousWebSocket: typeof window.WebSocket | null = null;
let previousEventSource: typeof window.EventSource | null = null;
let rootFetch: typeof window.fetch | null = null;

const ROUTE_MODULES: ReadonlyArray<readonly [string, OmnixModuleId]> = [
  ['/voice-cloning', 'voice-cloning'],
  ['/image-generation', 'image-generation'],
  ['/diagnostics', 'diagnostics'],
  ['/storyteller', 'storyteller'],
  ['/chatbot', 'chatbot'],
  ['/podcast', 'podcast'],
  ['/trading', 'trading'],
  ['/providers', 'providers'],
  ['/models', 'models'],
  ['/assets', 'assets'],
  ['/reports', 'reports'],
  ['/settings', 'settings'],
  ['/rpg', 'rpg'],
  ['/voice', 'voice'],
  ['/stt', 'stt'],
  ['/jobs', 'jobs'],
] as const;

// These are the API families each workspace is allowed to use. Keeping this
// list at the browser boundary prevents a globally installed controller from
// silently reaching another workspace's backend while the user is navigating.
const MODULE_API_PREFIXES: Record<OmnixModuleId, readonly string[]> = {
  rpg: ['/api/rpg', '/api/assets', '/api/jobs', '/api/reports', '/api/replay', '/api/hermes', '/api/agent', '/api/prompts'],
  chatbot: [
    '/api/chat', '/api/assistant', '/api/characters', '/api/character-avatar-generations',
    '/api/character-avatar-visemes', '/api/character-live2d', '/api/image-generation',
    '/api/live', '/api/live-chat', '/api/live-call', '/api/tts', '/api/voice',
    '/api/voice-profiles', '/api/voice-library', '/api/assets', '/api/jobs', '/api/providers',
    '/api/settings', '/api/hermes', '/api/agent', '/api/prompts', '/api/desktop-companion',
  ],
  storyteller: ['/api/storyteller', '/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/tts', '/api/voice', '/api/agent', '/api/prompts'],
  podcast: ['/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/tts', '/api/voice', '/api/agent', '/api/prompts'],
  voice: ['/api/voice', '/api/voice-cloning', '/api/voice-library', '/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/tts', '/api/agent', '/api/prompts'],
  'voice-cloning': ['/api/voice-cloning', '/api/voice-library', '/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/tts', '/api/agent', '/api/prompts'],
  stt: ['/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/voice', '/api/tts', '/api/agent', '/api/prompts'],
  'image-generation': ['/api/image-generation', '/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/workers', '/api/agent', '/api/prompts'],
  trading: ['/api/trading'],
  providers: ['/api/providers', '/api/models', '/api/jobs', '/api/settings', '/api/health', '/api/diagnostics'],
  models: ['/api/models', '/api/providers', '/api/jobs', '/api/settings', '/api/health', '/api/diagnostics'],
  jobs: ['/api/jobs', '/api/assets', '/api/reports', '/api/diagnostics'],
  assets: ['/api/assets', '/api/jobs', '/api/reports'],
  reports: ['/api/reports', '/api/assets', '/api/jobs', '/api/replay'],
  settings: ['/api/settings', '/api/providers', '/api/models', '/api/runtime', '/api/assistant', '/api/hermes', '/api/diagnostics', '/api/workers'],
  diagnostics: ['/api/diagnostics', '/api/health', '/api/runtime', '/api/providers', '/api/models', '/api/jobs'],
};

function pathMatchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function moduleIdFromPathname(pathname: string): OmnixModuleId {
  const normalized = pathname.split('?', 1)[0].replace(/\/+$/u, '') || '/';
  return ROUTE_MODULES.find(([route]) => normalized === route || normalized.startsWith(`${route}/`))?.[1] ?? 'chatbot';
}

export function activeViewModule(): OmnixModuleId {
  if (typeof window === 'undefined') return 'chatbot';
  return moduleIdFromPathname(window.location.pathname);
}

export function setActiveViewModule(moduleId: OmnixModuleId): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.omnixActiveModule = moduleId;
}

export function isActiveView(moduleId: OmnixModuleId): boolean {
  return activeViewModule() === moduleId;
}

export function apiPath(input: RequestInfo | URL): string {
  const rawUrl = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  try {
    const base = typeof window === 'undefined' ? 'http://localhost/' : window.location.href;
    return new URL(rawUrl, base).pathname;
  } catch {
    return rawUrl.split('?', 1)[0];
  }
}

export function isApiAllowedForView(pathname: string, moduleId: OmnixModuleId): boolean {
  if (!pathname.startsWith('/api/')) return true;
  return MODULE_API_PREFIXES[moduleId].some((prefix) => pathMatchesPrefix(pathname, prefix));
}

function blockedApiResponse(pathname: string, moduleId: OmnixModuleId): Response {
  return new Response(JSON.stringify({
    code: 'VIEW_API_SCOPE_BLOCKED',
    detail: 'The active workspace cannot call this API family.',
    active_view: moduleId,
    request_path: pathname,
  }), {
    status: 403,
    headers: {
      'content-type': 'application/json',
      'x-omnix-view-api-blocked': 'true',
    },
  });
}

export function installViewApiFirewall(options: { outermost?: boolean } = {}): void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') return;
  const state = window as typeof window & Record<string, unknown>;
  if (options.outermost) {
    if (state[OUTER_VIEW_API_FIREWALL_KEY]) return;
  } else if (state[VIEW_API_FIREWALL_KEY]) return;

  if (!rootFetch) rootFetch = window.fetch.bind(window);
  if (!options.outermost) previousFetch = window.fetch;
  const delegate = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const pathname = apiPath(input);
    const moduleId = activeViewModule();
    if (!isApiAllowedForView(pathname, moduleId)) return blockedApiResponse(pathname, moduleId);
    if (options.outermost && moduleId === 'trading' && rootFetch) return rootFetch(input, init);
    return delegate(input, init);
  };

  if (!options.outermost) {
    const NativeWebSocket = window.WebSocket;
    if (typeof NativeWebSocket === 'function') {
      previousWebSocket = NativeWebSocket;
      class ScopedWebSocket extends NativeWebSocket {
        constructor(url: string | URL, protocols?: string | string[]) {
          const pathname = apiPath(String(url));
          if (!isApiAllowedForView(pathname, activeViewModule())) {
            throw new DOMException('The active workspace cannot open this API socket.', 'SecurityError');
          }
          super(url, protocols);
        }
      }
      window.WebSocket = ScopedWebSocket;
    }

    const NativeEventSource = window.EventSource;
    if (typeof NativeEventSource === 'function') {
      previousEventSource = NativeEventSource;
      class ScopedEventSource extends NativeEventSource {
        constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
          const pathname = apiPath(String(url));
          if (!isApiAllowedForView(pathname, activeViewModule())) {
            throw new DOMException('The active workspace cannot open this API stream.', 'SecurityError');
          }
          super(url, eventSourceInitDict);
        }
      }
      window.EventSource = ScopedEventSource;
    }
  }
  if (options.outermost) state[OUTER_VIEW_API_FIREWALL_KEY] = true;
  else state[VIEW_API_FIREWALL_KEY] = true;
}

export function resetViewApiFirewallForTests(): void {
  if (typeof window !== 'undefined' && previousFetch) window.fetch = previousFetch;
  if (typeof window !== 'undefined' && previousWebSocket) window.WebSocket = previousWebSocket;
  if (typeof window !== 'undefined' && previousEventSource) window.EventSource = previousEventSource;
  previousFetch = null;
  previousWebSocket = null;
  previousEventSource = null;
  rootFetch = null;
  if (typeof window !== 'undefined') {
    delete (window as typeof window & Record<string, unknown>)[VIEW_API_FIREWALL_KEY];
    delete (window as typeof window & Record<string, unknown>)[OUTER_VIEW_API_FIREWALL_KEY];
  }
}
