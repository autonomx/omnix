const LEGACY_SPECULATION_STREAM_PATH = /^\/api\/live\/speculation\/sessions\/([^/]+)\/stream$/;
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const INSTALLED_KEY = '__omnixLiveSpeculationHandshakeTransportInstalled';

type HandshakeTransportWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationHandshakeTransportInstalled?: boolean;
};

type SpeculationHandshake = {
  ok?: boolean;
  generation_id?: string;
  segment_id?: string;
  source_sequence?: number;
  provider_id?: string | null;
  model_id?: string | null;
};

let previousFetch: typeof window.fetch | null = null;

export function initializeLiveSpeculationHandshakeTransport(): () => void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') {
    return () => undefined;
  }
  const liveWindow = window as HandshakeTransportWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  previousFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const fetchImpl = previousFetch ?? window.fetch.bind(window);
    const bridged = await bridgeLiveSpeculationHandshakeRequest(fetchImpl, input, init);
    return bridged ?? fetchImpl(input, init);
  };

  return () => {
    if (previousFetch) window.fetch = previousFetch;
    previousFetch = null;
    liveWindow[INSTALLED_KEY] = false;
  };
}

export async function bridgeLiveSpeculationHandshakeRequest(
  fetchImpl: typeof fetch,
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response | null> {
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (method !== 'POST') return null;

  const rawUrl = typeof input === 'string' || input instanceof URL
    ? input.toString()
    : input.url;
  const baseUrl = typeof window !== 'undefined'
    ? window.location.origin
    : 'http://localhost';
  const url = new URL(rawUrl, baseUrl);
  const match = LEGACY_SPECULATION_STREAM_PATH.exec(url.pathname);
  if (!match) return null;

  const requestBody = await requestBodyText(input, init);
  if (!requestBody) return null;

  const sessionId = decodeURIComponent(match[1]);
  const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
  const inlineStartedAt = now();
  const inlineResponse = await fetchImpl(
    `/api/live/speculation/sessions/${encodeURIComponent(sessionId)}/start-stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: requestBody,
      signal,
    },
  );
  if (
    inlineResponse.ok
    && responseContentType(inlineResponse).startsWith('text/event-stream')
  ) {
    dispatchPerformance('llm_speculation_inline_stream_opened', {
      sessionId,
      openMs: now() - inlineStartedAt,
      transport: inlineResponse.headers.get('X-Omnix-Speculation-Transport')
        ?? 'inline-v1',
    });
    return inlineResponse;
  }
  if (inlineResponse.status !== 404 && inlineResponse.status !== 405) {
    return inlineResponse;
  }

  const handshakeStartedAt = now();
  const startResponse = await fetchImpl(
    `/api/live/speculation/sessions/${encodeURIComponent(sessionId)}/start`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: requestBody,
      signal,
    },
  );
  if (!startResponse.ok) return startResponse;

  const handshake = await readHandshake(startResponse);
  if (!validHandshake(handshake)) return startResponse;

  dispatchPerformance('llm_speculation_handshake_ready', {
    sessionId,
    generationId: handshake.generation_id,
    handshakeMs: now() - handshakeStartedAt,
    transport: 'two-request-fallback',
  });
  return createBridgedSpeculationResponse(fetchImpl, sessionId, handshake, signal);
}

function createBridgedSpeculationResponse(
  fetchImpl: typeof fetch,
  sessionId: string,
  handshake: Required<Pick<SpeculationHandshake, 'generation_id' | 'segment_id' | 'source_sequence'>>
    & SpeculationHandshake,
  sourceSignal?: AbortSignal | null,
): Response {
  const encoder = new TextEncoder();
  const abortController = new AbortController();
  let closed = false;
  let cancellationSent = false;

  const cancelGeneration = () => {
    if (cancellationSent) return;
    cancellationSent = true;
    void requestGenerationCancellation(
      fetchImpl,
      sessionId,
      handshake.generation_id,
    );
  };

  if (sourceSignal) {
    const abort = () => {
      abortController.abort(sourceSignal.reason);
      cancelGeneration();
    };
    if (sourceSignal.aborted) abort();
    else sourceSignal.addEventListener('abort', abort, { once: true });
  }

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(sse({
        type: 'speculation_started',
        generation_id: handshake.generation_id,
        segment_id: handshake.segment_id,
        source_sequence: handshake.source_sequence,
        provider_id: handshake.provider_id ?? null,
        model_id: handshake.model_id ?? null,
      })));

      const attachStartedAt = now();
      void pipeGenerationStream(
        fetchImpl,
        sessionId,
        handshake.generation_id,
        abortController.signal,
        (chunk) => {
          if (!closed) controller.enqueue(chunk);
        },
      ).then(() => {
        dispatchPerformance('llm_speculation_stream_attached', {
          sessionId,
          generationId: handshake.generation_id,
          streamLifetimeMs: now() - attachStartedAt,
          transport: 'two-request-fallback',
        });
        if (!closed) {
          closed = true;
          controller.close();
        }
      }).catch((error: unknown) => {
        if (closed) return;
        if (abortController.signal.aborted) {
          closed = true;
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(sse({
          type: 'error',
          generation_id: handshake.generation_id,
          message: error instanceof Error
            ? error.message
            : 'Speculative generation stream failed.',
        })));
        controller.enqueue(encoder.encode(sse({
          type: 'done',
          generation_id: handshake.generation_id,
        })));
        closed = true;
        controller.close();
      });
    },
    cancel(reason) {
      closed = true;
      abortController.abort(reason);
      cancelGeneration();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-store',
      'X-Omnix-Speculation-Transport': 'two-request-fallback',
    },
  });
}

async function pipeGenerationStream(
  fetchImpl: typeof fetch,
  sessionId: string,
  generationId: string,
  signal: AbortSignal,
  emit: (chunk: Uint8Array) => void,
): Promise<void> {
  const response = await fetchImpl(
    `/api/live/speculation/sessions/${encodeURIComponent(sessionId)}/${encodeURIComponent(generationId)}/stream`,
    {
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
      signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error(`Speculation generation stream failed with status ${response.status}.`);
  }

  const reader = response.body.getReader();
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value?.byteLength) emit(value);
    }
  } finally {
    reader.releaseLock();
  }
}

async function requestGenerationCancellation(
  fetchImpl: typeof fetch,
  sessionId: string,
  generationId: string,
): Promise<void> {
  try {
    await fetchImpl(
      `/api/live/speculation/sessions/${encodeURIComponent(sessionId)}/${encodeURIComponent(generationId)}/cancel`,
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        keepalive: true,
      },
    );
  } catch {
    // Cancellation is best effort; the server also cancels on stream detach/TTL.
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

async function readHandshake(response: Response): Promise<SpeculationHandshake | null> {
  try {
    const payload = await response.json() as unknown;
    return payload && typeof payload === 'object'
      ? payload as SpeculationHandshake
      : null;
  } catch {
    return null;
  }
}

function validHandshake(
  handshake: SpeculationHandshake | null,
): handshake is Required<Pick<SpeculationHandshake, 'generation_id' | 'segment_id' | 'source_sequence'>>
  & SpeculationHandshake {
  return Boolean(
    handshake
    && handshake.ok !== false
    && typeof handshake.generation_id === 'string'
    && handshake.generation_id.length > 0
    && typeof handshake.segment_id === 'string'
    && handshake.segment_id.length > 0
    && typeof handshake.source_sequence === 'number',
  );
}

function responseContentType(response: Response): string {
  return (response.headers.get('Content-Type') ?? '').toLowerCase();
}

function sse(payload: Record<string, unknown>): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function dispatchPerformance(stage: string, detail: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}
