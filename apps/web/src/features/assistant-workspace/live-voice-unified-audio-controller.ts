import { stopAssistantPcmStream } from './assistant-pcm-stream-websocket-player';
import {
  createLiveCallDiagnosticsReporter,
  createLiveCallTraceId,
  type LiveCallDiagnosticsReporter,
} from './live-call-diagnostics-client';
import {
  createLiveVoicePcmSession,
  type LiveVoicePcmSession,
} from './live-voice-pcm-session';

const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages\/stream$/;
const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const LIVE_VOICE_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const VOICE_SETTINGS_KEY = 'omnix.chatbot.assistantSettings';
const MIN_SENTENCE_CHARS = 36;
const MAX_PHRASE_CHARS = 120;

type ChatStreamEvent = {
  type?: string;
  text?: string;
};

type LiveVoiceWindow = Window & typeof globalThis & {
  __omnixLiveVoiceUnifiedAudioInstalled?: boolean;
};

type ActiveLiveTurn = {
  generation: number;
  traceId: string;
  startedAtMs: number;
  reporter: LiveCallDiagnosticsReporter;
  sessionPromise: Promise<LiveVoicePcmSession>;
  phraseCount: number;
  textChunkCount: number;
};

let originalFetch: typeof window.fetch | null = null;
let playbackGeneration = 0;
let activeTurn: ActiveLiveTurn | null = null;

export function initializeLiveVoiceUnifiedAudioController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const liveWindow = window as LiveVoiceWindow;
  if (liveWindow.__omnixLiveVoiceUnifiedAudioInstalled) return () => undefined;
  liveWindow.__omnixLiveVoiceUnifiedAudioInstalled = true;

  originalFetch = window.fetch.bind(window);
  window.fetch = interceptLiveVoiceFetch;
  window.addEventListener(LIVE_VOICE_INTERRUPT_EVENT, stopLiveVoiceUnifiedAudio);
  window.addEventListener(LIVE_VOICE_STOP_EVENT, stopLiveVoiceUnifiedAudio);
  window.addEventListener('beforeunload', stopLiveVoiceUnifiedAudio);
  const installedReporter = createLiveCallDiagnosticsReporter('live-call:controller');
  installedReporter.record('controller_installed', {
    location: window.location.href,
    fetch_wrapped: window.fetch === interceptLiveVoiceFetch,
  }, 'controller');
  void installedReporter.close('controller_install_confirmed');

  return () => {
    if (originalFetch) window.fetch = originalFetch;
    originalFetch = null;
    window.removeEventListener(LIVE_VOICE_INTERRUPT_EVENT, stopLiveVoiceUnifiedAudio);
    window.removeEventListener(LIVE_VOICE_STOP_EVENT, stopLiveVoiceUnifiedAudio);
    window.removeEventListener('beforeunload', stopLiveVoiceUnifiedAudio);
    stopLiveVoiceUnifiedAudio();
    liveWindow.__omnixLiveVoiceUnifiedAudioInstalled = false;
  };
}

async function interceptLiveVoiceFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  const response = await fetchImpl(input, init);
  if (!shouldUseUnifiedLiveVoiceAudio(input, init) || !response.body || !response.ok) return response;

  void stopActiveTurn('superseded-by-new-turn');
  stopAssistantPcmStream(document);
  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, window.location.origin);
  const sessionId = CHAT_STREAM_PATH.exec(url.pathname)?.[1] ?? 'unknown';
  const generation = ++playbackGeneration;
  const traceId = createLiveCallTraceId(sessionId);
  const reporter = createLiveCallDiagnosticsReporter(traceId);
  const voiceId = selectedVoiceId();
  const startedAtMs = performance.now();
  const sessionPromise = createLiveVoicePcmSession(traceId, voiceId, reporter);
  activeTurn = {
    generation,
    traceId,
    startedAtMs,
    reporter,
    sessionPromise,
    phraseCount: 0,
    textChunkCount: 0,
  };
  reporter.record('turn_intercepted', {
    session_id: sessionId,
    request_path: url.pathname,
    voice_id: voiceId,
    auto_speak: true,
  }, 'controller');

  const [applicationBranch, audioBranch] = response.body.tee();
  void consumeLiveVoiceText(audioBranch, activeTurn).catch(async (error: unknown) => {
    if (generation !== playbackGeneration) return;
    const message = error instanceof Error ? error.message : 'Live voice audio streaming failed.';
    reporter.record('turn_failed', { error: message }, 'controller');
    setInlineStatus(message);
    setVoiceSpeaking(false);
    const session = await sessionPromise.catch(() => null);
    await session?.stop('turn-failed');
    await reporter.close('turn_failed_final', { error: message });
    if (activeTurn?.generation === generation) activeTurn = null;
  });

  const headers = new Headers(response.headers);
  headers.delete('content-length');
  return new Response(filterLegacyAudioTextChunks(applicationBranch), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function shouldUseUnifiedLiveVoiceAudio(input: RequestInfo | URL, init?: RequestInit): boolean {
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (method !== 'POST') return false;
  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, window.location.origin);
  return CHAT_STREAM_PATH.test(url.pathname) && isAutoSpeakEnabled();
}

async function consumeLiveVoiceText(stream: ReadableStream<Uint8Array>, turn: ActiveLiveTurn): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let phrase = '';

  while (turn.generation === playbackGeneration) {
    const { value, done } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    const blocks = pending.split(/\n\n/);
    pending = blocks.pop() ?? '';
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event?.type !== 'text_chunk' || typeof event.text !== 'string') continue;
      turn.textChunkCount += 1;
      turn.reporter.record('llm_text_chunk_received', {
        text_chunk_index: turn.textChunkCount - 1,
        text: event.text,
        text_length: event.text.length,
        elapsed_ms: performance.now() - turn.startedAtMs,
      }, 'controller');
      phrase = mergeText(phrase, event.text);
      if (shouldFlushPhrase(phrase)) {
        queuePhrase(phrase, turn, 'boundary');
        phrase = '';
      }
    }
  }

  pending += decoder.decode();
  if (pending.trim()) {
    const event = parseSseBlock(pending);
    if (event?.type === 'text_chunk' && typeof event.text === 'string') {
      turn.textChunkCount += 1;
      phrase = mergeText(phrase, event.text);
    }
  }
  if (phrase.trim()) queuePhrase(phrase, turn, 'stream-end');
  turn.reporter.record('llm_stream_finished', {
    elapsed_ms: performance.now() - turn.startedAtMs,
    text_chunks: turn.textChunkCount,
    phrases: turn.phraseCount,
  }, 'controller');

  const session = await turn.sessionPromise;
  await session.finish();
  if (turn.generation !== playbackGeneration) return;
  setVoiceSpeaking(false);
  setInlineStatus('Live response audio finished.');
  await turn.reporter.close('turn_finished', {
    elapsed_ms: performance.now() - turn.startedAtMs,
    text_chunks: turn.textChunkCount,
    phrases: turn.phraseCount,
  });
  if (activeTurn?.generation === turn.generation) activeTurn = null;
}

function queuePhrase(text: string, turn: ActiveLiveTurn, reason: string): void {
  const phrase = text.trim();
  if (!phrase || turn.generation !== playbackGeneration) return;
  const phraseIndex = turn.phraseCount;
  turn.phraseCount += 1;
  setVoiceSpeaking(true);
  setInlineStatus('Buffering live response audio…');
  turn.reporter.record('phrase_queued', {
    phrase_index: phraseIndex,
    reason,
    text: phrase,
    text_length: phrase.length,
    elapsed_ms: performance.now() - turn.startedAtMs,
  }, 'controller');
  void turn.sessionPromise.then((session) => session.enqueuePhrase(phrase, phraseIndex)).catch((error: unknown) => {
    turn.reporter.record('phrase_queue_failed', {
      phrase_index: phraseIndex,
      error: error instanceof Error ? error.message : String(error),
    }, 'controller');
  });
}

function stopLiveVoiceUnifiedAudio(event?: Event): void {
  const reason = event?.type === LIVE_VOICE_INTERRUPT_EVENT ? 'voice-interrupt' : 'live-call-stop';
  playbackGeneration += 1;
  void stopActiveTurn(reason);
  stopAssistantPcmStream(document);
  setVoiceSpeaking(false);
}

async function stopActiveTurn(reason: string): Promise<void> {
  const turn = activeTurn;
  activeTurn = null;
  if (!turn) return;
  turn.reporter.record('turn_stop_requested', {
    reason,
    elapsed_ms: performance.now() - turn.startedAtMs,
    text_chunks: turn.textChunkCount,
    phrases: turn.phraseCount,
  }, 'controller');
  const session = await turn.sessionPromise.catch(() => null);
  await session?.stop(reason);
  await turn.reporter.close('turn_stopped', { reason });
}

function isAutoSpeakEnabled(): boolean {
  return document.querySelector<HTMLInputElement>('.assistant-voice-toggle input[type="checkbox"]')?.checked ?? false;
}

function setVoiceSpeaking(speaking: boolean): void {
  document.querySelectorAll<HTMLElement>('.assistant-voice-orb').forEach((orb) => {
    const card = orb.closest<HTMLElement>('.assistant-live-card');
    const live = card?.dataset.liveVoiceStatus === 'connected'
      || Array.from(card?.querySelectorAll<HTMLButtonElement>('button') ?? []).some(
        (button) => button.textContent?.trim().toLowerCase() === 'end call',
      );
    orb.dataset.voiceMode = speaking ? 'speaking' : live ? 'listening' : 'idle';
  });
}

function setInlineStatus(message: string): void {
  const host = document.querySelector<HTMLElement>('.assistant-inline-status');
  if (!host) return;
  let status = host.querySelector<HTMLElement>('[data-omnix-live-voice-stream-status]');
  if (!status) {
    status = document.createElement('span');
    status.setAttribute('data-omnix-live-voice-stream-status', 'true');
    status.setAttribute('role', 'status');
    host.appendChild(status);
  }
  status.textContent = message;
}

function filterLegacyAudioTextChunks(stream: ReadableStream<Uint8Array>): ReadableStream<Uint8Array> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let pending = '';

  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          pending += decoder.decode();
          if (pending.trim() && parseSseBlock(pending)?.type !== 'text_chunk') controller.enqueue(encoder.encode(pending));
          controller.close();
          return;
        }
        pending += decoder.decode(value, { stream: true });
        const blocks = pending.split(/\n\n/);
        pending = blocks.pop() ?? '';
        const forwarded = blocks
          .filter((block) => parseSseBlock(block)?.type !== 'text_chunk')
          .map((block) => `${block}\n\n`)
          .join('');
        if (forwarded) {
          controller.enqueue(encoder.encode(forwarded));
          return;
        }
      }
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });
}

function parseSseBlock(block: string): ChatStreamEvent | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return null;
  try { return JSON.parse(data) as ChatStreamEvent; } catch { return null; }
}

function mergeText(current: string, next: string): string {
  const left = current.trim();
  const right = next.trim();
  if (!left) return right;
  if (!right) return left;
  return `${left} ${right}`;
}

function shouldFlushPhrase(text: string): boolean {
  const phrase = text.trim();
  if (phrase.length >= MAX_PHRASE_CHARS) return true;
  return phrase.length >= MIN_SENTENCE_CHARS && /[.!?][\]})"'’”]*$/.test(phrase);
}

function selectedVoiceId(): string | null {
  const mounted = document.querySelector<HTMLSelectElement>('select[aria-label="Cloned voice"]')?.value.trim();
  if (mounted) return mounted;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(VOICE_SETTINGS_KEY) || '{}') as { voiceId?: unknown };
    return typeof parsed.voiceId === 'string' && parsed.voiceId.trim() ? parsed.voiceId.trim() : null;
  } catch {
    return null;
  }
}
