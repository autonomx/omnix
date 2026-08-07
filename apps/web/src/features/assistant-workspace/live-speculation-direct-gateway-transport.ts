const SPECULATION_PATH = /^\/api\/live\/speculation(?:\/|$)/;
const INSTALLED_KEY = '__omnixLiveSpeculationDirectGatewayTransportInstalled';
const DEFAULT_DIRECT_GATEWAY_ORIGIN = 'http://127.0.0.1:8000';
const PERF_EVENT = 'omnix:assistant-voice-perf';

type DirectGatewayWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationDirectGatewayTransportInstalled?: boolean;
};

type LocationLike = Pick<Location, 'hostname' | 'port' | 'origin'>;
type EnvLike = Record<string, string | boolean | number | undefined>;

let previousFetch: typeof window.fetch | null = null;

export function initializeLiveSpeculationDirectGatewayTransport(): () => void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') {
    return () => undefined;
  }
  const liveWindow = window as DirectGatewayWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  previousFetch = window.fetch.bind(window);
  window.fetch = directSpeculationFetch;

  return () => {
    if (previousFetch) window.fetch = previousFetch;
    previousFetch = null;
    liveWindow[INSTALLED_KEY] = false;
  };
}

export async function directSpeculationFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const fetchImpl = previousFetch ?? window.fetch.bind(window);
  const directUrl = resolveDirectSpeculationUrl(input);
  if (!directUrl) return fetchImpl(input, init);

  const startedAt = now();
  try {
    const response = await fetchImpl(directUrl, init);
    dispatchPerformance(stageFor(input, 'response'), {
      directGateway: true,
      directOrigin: new URL(directUrl).origin,
      elapsedMs: now() - startedAt,
      status: response.status,
    });
    return response;
  } catch (error: unknown) {
    if (init?.signal?.aborted) throw error;
    dispatchPerformance(stageFor(input, 'fallback'), {
      directGateway: true,
      elapsedMs: now() - startedAt,
      error: error instanceof Error ? error.name : typeof error,
    });
    return fetchImpl(input, init);
  }
}

export function resolveDirectSpeculationUrl(
  input: RequestInfo | URL,
  locationLike: LocationLike = window.location,
  env: EnvLike = importMetaEnv(),
): string | null {
  // Request instances may contain a one-shot body stream. Keep them untouched;
  // all latency-critical speculation calls currently use string paths.
  if (input instanceof Request) return null;
  if (!directGatewayEnabled(locationLike, env)) return null;

  const rawUrl = typeof input === 'string' || input instanceof URL
    ? input.toString()
    : '';
  const url = new URL(rawUrl, locationLike.origin);
  if (url.origin !== locationLike.origin || !SPECULATION_PATH.test(url.pathname)) {
    return null;
  }

  const configuredOrigin = stringEnv(env, 'VITE_LIVE_SPECULATION_GATEWAY_ORIGIN');
  const directOrigin = normalizeOrigin(configuredOrigin ?? DEFAULT_DIRECT_GATEWAY_ORIGIN);
  if (!directOrigin || directOrigin === locationLike.origin) return null;
  return `${directOrigin}${url.pathname}${url.search}${url.hash}`;
}

export function directGatewayEnabled(
  locationLike: LocationLike,
  env: EnvLike = importMetaEnv(),
): boolean {
  const explicit = booleanEnv(env, 'VITE_LIVE_SPECULATION_DIRECT_GATEWAY');
  if (explicit === false) return false;
  const hostname = locationLike.hostname.trim().toLowerCase();
  const localHost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
  if (!localHost) return false;
  if (explicit === true) return true;
  // Default only for the local Vite dev/preview origins. Production and packaged
  // clients continue using the normal same-origin gateway path.
  return locationLike.port === '5173' || locationLike.port === '4173';
}

function stageFor(input: RequestInfo | URL, suffix: 'response' | 'fallback'): string {
  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : '';
  const tts = rawUrl.includes('/tts-prefetch');
  return `${tts ? 'tts_speculative' : 'llm_speculation'}_direct_gateway_${suffix}`;
}

function normalizeOrigin(value: string): string | null {
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function importMetaEnv(): EnvLike {
  return ((import.meta as unknown as { env?: EnvLike }).env ?? {}) as EnvLike;
}

function stringEnv(env: EnvLike, key: string): string | undefined {
  const value = env[key];
  if (value === undefined || value === false) return undefined;
  const text = String(value).trim();
  return text || undefined;
}

function booleanEnv(env: EnvLike, key: string): boolean | undefined {
  const value = env[key];
  if (value === undefined) return undefined;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = String(value).trim().toLowerCase();
  if (['1', 'true', 'yes', 'on', 'enabled'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'disabled'].includes(normalized)) return false;
  return undefined;
}

function dispatchPerformance(stage: string, detail: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}
