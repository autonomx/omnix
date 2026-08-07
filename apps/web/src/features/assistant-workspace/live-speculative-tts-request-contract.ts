const SPECULATIVE_TTS_PREFETCH_PATH = '/api/live/speculation/tts-prefetch';
const INSTALLED_KEY = '__omnixLiveSpeculativeTtsRequestContractInstalled';

// These fields are part of the server-side speculative TTS cache key. Keep
// prefetch synthesis aligned with the accepted live-call websocket request so
// completed speculative PCM can actually be claimed after final acceptance.
const ACCEPTED_LIVE_TTS_CONTRACT = Object.freeze({
  chunk_size: 4,
  temperature: 0.6,
  top_k: 20,
  top_p: 0.85,
  repetition_penalty: 1.05,
  append_silence: false,
  non_streaming_mode: false,
  parity_mode: false,
});

type ContractWindow = Window & typeof globalThis & {
  __omnixLiveSpeculativeTtsRequestContractInstalled?: boolean;
};

type PrefetchPayload = Record<string, unknown> & {
  request?: Record<string, unknown>;
};

let previousFetch: typeof window.fetch | null = null;

export function initializeLiveSpeculativeTtsRequestContract(): () => void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') {
    return () => undefined;
  }
  const liveWindow = window as ContractWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  previousFetch = window.fetch.bind(window);
  window.fetch = normalizeSpeculativeTtsFetch;

  return () => {
    if (previousFetch) window.fetch = previousFetch;
    previousFetch = null;
    liveWindow[INSTALLED_KEY] = false;
  };
}

export async function normalizeSpeculativeTtsFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const fetchImpl = previousFetch ?? window.fetch.bind(window);
  const normalized = await normalizeSpeculativeTtsRequest(input, init);
  return fetchImpl(normalized.input, normalized.init);
}

export async function normalizeSpeculativeTtsRequest(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<{ input: RequestInfo | URL; init?: RequestInit }> {
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (method !== 'POST') return { input, init };

  const rawUrl = typeof input === 'string' || input instanceof URL
    ? input.toString()
    : input.url;
  const baseUrl = typeof window !== 'undefined'
    ? window.location.origin
    : 'http://localhost';
  const url = new URL(rawUrl, baseUrl);
  if (url.pathname !== SPECULATIVE_TTS_PREFETCH_PATH) return { input, init };

  const body = await requestBodyText(input, init);
  const payload = parsePrefetchPayload(body);
  if (!payload?.request) return { input, init };

  const normalizedBody = JSON.stringify({
    ...payload,
    request: {
      ...payload.request,
      ...ACCEPTED_LIVE_TTS_CONTRACT,
    },
  });

  if (input instanceof Request) {
    const request = new Request(input, {
      ...init,
      body: normalizedBody,
      // Keep this latency-critical control request eligible for the browser's
      // highest fetch priority without changing transport semantics.
      priority: 'high' as RequestPriority,
    });
    return { input: request };
  }

  return {
    input,
    init: {
      ...init,
      body: normalizedBody,
      priority: 'high' as RequestPriority,
    },
  };
}

function parsePrefetchPayload(body: string | null): PrefetchPayload | null {
  if (!body) return null;
  try {
    const parsed = JSON.parse(body) as unknown;
    return parsed && typeof parsed === 'object'
      ? parsed as PrefetchPayload
      : null;
  } catch {
    return null;
  }
}

async function requestBodyText(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<string | null> {
  if (typeof init?.body === 'string') return init.body;
  if (input instanceof Request) {
    try {
      return await input.clone().text();
    } catch {
      return null;
    }
  }
  return null;
}

export const SPECULATIVE_TTS_ACCEPTED_REQUEST_CONTRACT = ACCEPTED_LIVE_TTS_CONTRACT;
