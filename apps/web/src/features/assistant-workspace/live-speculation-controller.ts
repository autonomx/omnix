import {
  LIVE_STT_SPECULATION_CANDIDATE_EVENT,
  LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT,
  LIVE_STT_SPECULATION_FINAL_EVENT,
  LIVE_STT_SPECULATION_PARTIAL_EVENT,
} from './live-stt-authority-controller';

const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages\/stream$/;
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const INSTALLED_KEY = '__omnixLiveSpeculationInstalled';
const CORRECTION_PATTERN = /(?:^|\s)(?:uh+|um+|erm+|wait|sorry|actually|correction|no[,. ]+i mean)(?:\s|$)/i;
const WORD_PATTERN = /[\p{L}\p{N}_]+(?:['’][\p{L}\p{N}_]+)?/gu;

type SpeculationWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationInstalled?: boolean;
};

type SttPartialDetail = {
  chatSessionId?: string;
  segmentId?: string;
  sourceSequence?: number;
  text?: string;
};

type SttCandidateDetail = SttPartialDetail & {
  probability?: number;
  modelTimeMs?: number;
};

type SpeculationEvent = {
  type?: string;
  generation_id?: string;
  text?: string;
  content?: string;
  message?: string;
  provider_id?: string | null;
  model_id?: string | null;
};

type AcceptedSpeculation = {
  ok: boolean;
  generation_id: string;
  content: string;
  user_message: Record<string, unknown>;
  session: Record<string, unknown>;
};

type ChatStreamRequestBody = Record<string, unknown> & {
  content?: string;
  provider_id?: string;
  model_id?: string;
  agent_mode?: boolean;
  dry_run?: boolean;
  research_mode?: string | null;
  user_turn_id?: string;
  speech_segment_id?: string;
  live_voice_turn_id?: string;
};

type ActiveSpeculation = {
  sessionId: string;
  segmentId: string;
  sourceSequence: number;
  candidateText: string;
  providerId: string | null;
  modelId: string | null;
  generationId: string | null;
  chunks: string[];
  subscribers: Set<() => void>;
  abortController: AbortController;
  startedPromise: Promise<void>;
  resolveStarted: () => void;
  generationPromise: Promise<void>;
  resolveGeneration: () => void;
  finalText: string | null;
  completed: boolean;
  error: string | null;
  reused: boolean;
  acceptBody: ChatStreamRequestBody | null;
};

let originalFetch: typeof window.fetch | null = null;
let activeSpeculation: ActiveSpeculation | null = null;
const partials = new Map<string, string>();

export function normalizeSpeculationWords(text: string): string[] {
  return [...text.matchAll(WORD_PATTERN)]
    .map((match) => match[0].toLowerCase())
    .map((token) => token.replaceAll('’', "'"));
}

export function transcriptIsSpeculationSafe(text: string): boolean {
  return normalizeSpeculationWords(text).length >= 2 && !CORRECTION_PATTERN.test(text);
}

export function transcriptsCanReuseSpeculation(candidate: string, final: string): boolean {
  if (!transcriptIsSpeculationSafe(candidate)) return false;
  const left = normalizeSpeculationWords(candidate);
  const right = normalizeSpeculationWords(final);
  return left.length === right.length && left.every((word, index) => word === right[index]);
}

export function speculationRequestCanReuse(
  body: ChatStreamRequestBody | null,
  speculativeProviderId: string | null,
  speculativeModelId: string | null,
): boolean {
  if (!body) return false;
  if (body.agent_mode === true || body.dry_run === true || body.research_mode) {
    return false;
  }
  const providerId = typeof body.provider_id === 'string' ? body.provider_id : null;
  const modelId = typeof body.model_id === 'string' ? body.model_id : null;
  if (providerId && providerId !== speculativeProviderId) return false;
  if (modelId && modelId !== speculativeModelId) return false;
  return true;
}

export function initializeLiveSpeculationController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as SpeculationWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  originalFetch = window.fetch.bind(window);
  window.fetch = interceptChatStream;

  const handlePartial = (event: Event): void => {
    const detail = (event as CustomEvent<SttPartialDetail>).detail;
    const key = partialKey(detail);
    const text = detail?.text?.trim();
    if (!key || !text) return;
    partials.set(key, text);
    const active = activeSpeculation;
    if (!active || active.segmentId !== detail.segmentId || active.sourceSequence !== detail.sourceSequence) return;
    if (normalizeComparable(text) !== normalizeComparable(active.candidateText)) {
      cancelSpeculation('transcript_resumed_or_corrected');
    }
  };

  const handleCandidate = (event: Event): void => {
    if (!speculationEnabled()) return;
    const detail = (event as CustomEvent<SttCandidateDetail>).detail;
    const key = partialKey(detail);
    if (!key || !detail.chatSessionId || !detail.segmentId || typeof detail.sourceSequence !== 'number') return;
    const candidateText = partials.get(key)?.trim() ?? '';
    if (!transcriptIsSpeculationSafe(candidateText)) return;
    if (activeSpeculation
      && activeSpeculation.segmentId === detail.segmentId
      && activeSpeculation.sourceSequence === detail.sourceSequence) return;
    cancelSpeculation('superseded_candidate');
    activeSpeculation = createSpeculation(
      detail.chatSessionId,
      detail.segmentId,
      detail.sourceSequence,
      candidateText,
    );
    consumeSpeculation(activeSpeculation, detail.probability).catch((error: unknown) => {
      const active = activeSpeculation;
      if (!active || active.segmentId !== detail.segmentId) return;
      active.error = error instanceof Error ? error.message : 'Speculative generation failed.';
      active.completed = true;
      active.resolveStarted();
      active.resolveGeneration();
      notify(active);
    });
  };

  const handleFinal = (event: Event): void => {
    const detail = (event as CustomEvent<SttPartialDetail>).detail;
    const active = activeSpeculation;
    const finalText = detail?.text?.trim() ?? '';
    if (!active || active.segmentId !== detail.segmentId || active.sourceSequence !== detail.sourceSequence) return;
    if (!transcriptsCanReuseSpeculation(active.candidateText, finalText)) {
      cancelSpeculation('final_transcript_mismatch');
      return;
    }
    active.finalText = finalText;
    dispatchPerformance('llm_speculation_final_accepted', {
      sessionId: active.sessionId,
      segmentId: active.segmentId,
      sourceSequence: active.sourceSequence,
      candidateChars: active.candidateText.length,
      finalChars: finalText.length,
    });
    notify(active);
  };

  const handleDeliverySettled = (event: Event): void => {
    const detail = (event as CustomEvent<SttPartialDetail>).detail;
    const active = activeSpeculation;
    const key = partialKey(detail);
    if (key) partials.delete(key);
    if (
      active
      && active.segmentId === detail?.segmentId
      && active.sourceSequence === detail.sourceSequence
      && !active.reused
    ) {
      cancelSpeculation('accepted_final_not_routed_to_chat');
    }
  };

  window.addEventListener(LIVE_STT_SPECULATION_PARTIAL_EVENT, handlePartial);
  window.addEventListener(LIVE_STT_SPECULATION_CANDIDATE_EVENT, handleCandidate);
  window.addEventListener(LIVE_STT_SPECULATION_FINAL_EVENT, handleFinal);
  window.addEventListener(
    LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT,
    handleDeliverySettled,
  );

  return () => {
    if (originalFetch) window.fetch = originalFetch;
    originalFetch = null;
    cancelSpeculation('controller_uninstalled');
    partials.clear();
    window.removeEventListener(LIVE_STT_SPECULATION_PARTIAL_EVENT, handlePartial);
    window.removeEventListener(LIVE_STT_SPECULATION_CANDIDATE_EVENT, handleCandidate);
    window.removeEventListener(LIVE_STT_SPECULATION_FINAL_EVENT, handleFinal);
    window.removeEventListener(
      LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT,
      handleDeliverySettled,
    );
    liveWindow[INSTALLED_KEY] = false;
  };
}

async function interceptChatStream(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, window.location.origin);
  const match = method === 'POST' ? CHAT_STREAM_PATH.exec(url.pathname) : null;
  if (!match) return fetchImpl(input, init);

  const body = await parseRequestBody(input, init);
  const finalText = typeof body?.content === 'string' ? body.content.trim() : '';
  const sessionId = decodeURIComponent(match[1]);
  const active = activeSpeculation;
  const transcriptMatches = Boolean(
    active
    && active.sessionId === sessionId
    && active.finalText
    && transcriptsCanReuseSpeculation(active.candidateText, finalText),
  );
  if (
    !active
    || active.reused
    || !transcriptMatches
    || active.error
    || !speculationRequestCanReuse(body, active.providerId, active.modelId)
  ) {
    if (active && active.sessionId === sessionId && active.finalText) {
      cancelSpeculation('final_request_not_compatible');
    }
    return fetchImpl(input, init);
  }

  await Promise.race([active.startedPromise, delay(120)]);
  if (!active.generationId || active.error) return fetchImpl(input, init);
  active.reused = true;
  active.acceptBody = body;
  dispatchPerformance('llm_speculation_reused', {
    sessionId,
    segmentId: active.segmentId,
    generationId: active.generationId,
    bufferedChunks: active.chunks.length,
  });
  return createAcceptedSpeculationResponse(active, fetchImpl);
}

function createSpeculation(
  sessionId: string,
  segmentId: string,
  sourceSequence: number,
  candidateText: string,
): ActiveSpeculation {
  let resolveStarted: () => void = () => {};
  let resolveGeneration: () => void = () => {};
  const startedPromise = new Promise<void>((resolve) => { resolveStarted = resolve; });
  const generationPromise = new Promise<void>((resolve) => { resolveGeneration = resolve; });
  return {
    sessionId,
    segmentId,
    sourceSequence,
    candidateText,
    providerId: null,
    modelId: null,
    generationId: null,
    chunks: [],
    subscribers: new Set(),
    abortController: new AbortController(),
    startedPromise,
    resolveStarted,
    generationPromise,
    resolveGeneration,
    finalText: null,
    completed: false,
    error: null,
    reused: false,
    acceptBody: null,
  };
}

async function consumeSpeculation(active: ActiveSpeculation, probability?: number): Promise<void> {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  dispatchPerformance('llm_speculation_started', {
    sessionId: active.sessionId,
    segmentId: active.segmentId,
    sourceSequence: active.sourceSequence,
    endpointProbability: probability,
    candidateChars: active.candidateText.length,
  });
  const response = await fetchImpl(
    `/api/live/speculation/sessions/${encodeURIComponent(active.sessionId)}/stream`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: active.candidateText,
        segment_id: active.segmentId,
        source_sequence: active.sourceSequence,
      }),
      signal: active.abortController.signal,
    },
  );
  if (!response.ok || !response.body) throw new Error(`Speculation stream failed with status ${response.status}.`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  try {
    while (!active.abortController.signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const blocks = pending.split(/\n\n/);
      pending = blocks.pop() ?? '';
      for (const block of blocks) applySpeculationEvent(active, parseSseBlock(block));
    }
    pending += decoder.decode();
    if (pending.trim()) applySpeculationEvent(active, parseSseBlock(pending));
  } finally {
    reader.releaseLock();
    active.completed = true;
    active.resolveStarted();
    active.resolveGeneration();
    notify(active);
  }
}

function applySpeculationEvent(active: ActiveSpeculation, event: SpeculationEvent | null): void {
  if (!event) return;
  if (event.type === 'speculation_started' && typeof event.generation_id === 'string') {
    active.generationId = event.generation_id;
    active.providerId = event.provider_id ?? null;
    active.modelId = event.model_id ?? null;
    active.resolveStarted();
    return;
  }
  if (event.type === 'text_chunk' && typeof event.text === 'string') {
    active.chunks.push(event.text);
    notify(active);
    return;
  }
  if (event.type === 'error') {
    active.error = event.message || 'Speculative generation failed.';
    notify(active);
  }
}

function createAcceptedSpeculationResponse(
  active: ActiveSpeculation,
  fetchImpl: typeof fetch,
): Response {
  const encoder = new TextEncoder();
  let cursor = 0;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      const emit = (payload: Record<string, unknown>): void => {
        if (!closed) controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`));
      };
      const flushChunks = (): void => {
        while (cursor < active.chunks.length) {
          emit({ type: 'text_chunk', text: active.chunks[cursor], speculative_reuse: true });
          cursor += 1;
        }
      };
      const update = (): void => flushChunks();
      active.subscribers.add(update);
      flushChunks();
      void active.generationPromise.then(async () => {
        flushChunks();
        if (active.error || !active.generationId || !active.finalText) {
          throw new Error(active.error || 'Speculation could not be accepted.');
        }
        const acceptedResponse = await fetchImpl(
          `/api/live/speculation/sessions/${encodeURIComponent(active.sessionId)}/${encodeURIComponent(active.generationId)}/accept`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              final_text: active.finalText,
              provider_id: bodyString(active.providerId),
              model_id: bodyString(active.modelId),
              user_turn_id: bodyString(active.acceptBody?.user_turn_id),
              speech_segment_id: bodyString(active.acceptBody?.speech_segment_id),
              live_voice_turn_id: bodyString(active.acceptBody?.live_voice_turn_id),
            }),
          },
        );
        if (!acceptedResponse.ok) throw new Error(`Speculation accept failed with status ${acceptedResponse.status}.`);
        const accepted = await acceptedResponse.json() as AcceptedSpeculation;
        emit({ type: 'user_message', user_message: accepted.user_message });
        emit({ type: 'session', session: accepted.session });
        emit({ type: 'done', speculative_reuse: true });
        dispatchPerformance('llm_speculation_committed', {
          sessionId: active.sessionId,
          generationId: active.generationId,
          responseChars: accepted.content.length,
        });
        closed = true;
        active.subscribers.delete(update);
        if (activeSpeculation === active) activeSpeculation = null;
        partials.delete(`${active.segmentId}:${active.sourceSequence}`);
        controller.close();
      }).catch((error: unknown) => {
        emit({ type: 'error', message: error instanceof Error ? error.message : 'Speculation reuse failed.' });
        closed = true;
        active.subscribers.delete(update);
        controller.close();
      });
    },
    cancel() {
      active.subscribers.clear();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' },
  });
}

function cancelSpeculation(reason: string): void {
  const active = activeSpeculation;
  activeSpeculation = null;
  if (!active) return;
  active.abortController.abort(reason);
  active.resolveStarted();
  active.resolveGeneration();
  active.subscribers.clear();
  dispatchPerformance('llm_speculation_cancelled', {
    sessionId: active.sessionId,
    segmentId: active.segmentId,
    generationId: active.generationId,
    reason,
  });
}

function notify(active: ActiveSpeculation): void {
  active.subscribers.forEach((subscriber) => subscriber());
}

function partialKey(detail: SttPartialDetail | undefined): string | null {
  if (!detail?.segmentId || typeof detail.sourceSequence !== 'number') return null;
  return `${detail.segmentId}:${detail.sourceSequence}`;
}

function normalizeComparable(text: string): string {
  return normalizeSpeculationWords(text).join(' ');
}

async function parseRequestBody(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<ChatStreamRequestBody | null> {
  const body = init?.body;
  if (typeof body === 'string') {
    try {
      const parsed = JSON.parse(body) as unknown;
      return parsed && typeof parsed === 'object'
        ? parsed as ChatStreamRequestBody
        : null;
    } catch {
      return null;
    }
  }
  if (input instanceof Request) {
    try {
      const parsed = await input.clone().json() as unknown;
      return parsed && typeof parsed === 'object'
        ? parsed as ChatStreamRequestBody
        : null;
    } catch {
      return null;
    }
  }
  return null;
}

function bodyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function parseSseBlock(block: string): SpeculationEvent | null {
  const data = block.split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return null;
  try { return JSON.parse(data) as SpeculationEvent; } catch { return null; }
}

function speculationEnabled(): boolean {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_LIVE_SPECULATION_ENABLED?.trim().toLowerCase() !== 'false';
}

function dispatchPerformance(stage: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
