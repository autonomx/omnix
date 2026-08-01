import { playBufferedTts, stopBufferedTtsPlayback } from './assistant-buffered-tts-player';
import { stopAssistantPcmStream } from './assistant-pcm-stream-websocket-player';
import { createLiveCallDiagnosticsReporter } from './live-call-diagnostics-client';
import { resolvePlaybackVoiceWithDiagnostics } from './voice-resolution-diagnostics';

const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages\/stream$/;
const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const LIVE_VOICE_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const INSTALLED_KEY = '__omnixLiveVoiceSmoothAudioInstalled';

type ChatStreamEvent = {
  type?: string;
  text?: string;
};

let originalFetch: typeof window.fetch | null = null;
let activeTurn: AbortController | null = null;

export function initializeLiveVoiceSmoothAudioController(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const state = window as typeof window & Record<string, unknown>;
  if (state[INSTALLED_KEY]) return () => undefined;
  state[INSTALLED_KEY] = true;

  originalFetch = window.fetch.bind(window);
  window.fetch = interceptLiveVoiceFetch;
  window.addEventListener(LIVE_VOICE_INTERRUPT_EVENT, stopLiveVoiceAudio);
  window.addEventListener(LIVE_VOICE_STOP_EVENT, stopLiveVoiceAudio);
  window.addEventListener('beforeunload', stopLiveVoiceAudio);

  return () => {
    if (originalFetch) window.fetch = originalFetch;
    originalFetch = null;
    window.removeEventListener(LIVE_VOICE_INTERRUPT_EVENT, stopLiveVoiceAudio);
    window.removeEventListener(LIVE_VOICE_STOP_EVENT, stopLiveVoiceAudio);
    window.removeEventListener('beforeunload', stopLiveVoiceAudio);
    stopLiveVoiceAudio();
    delete state[INSTALLED_KEY];
  };
}

async function interceptLiveVoiceFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  if (!shouldUseSmoothLiveVoiceAudio(input, init)) return fetchImpl(input, init);

  stopLiveVoiceAudio();
  stopAssistantPcmStream(document);
  const abortController = new AbortController();
  activeTurn = abortController;
  connectAbortSignal(init?.signal, abortController);

  try {
    const response = await fetchImpl(input, { ...init, signal: abortController.signal });
    if (!response.ok || !response.body) {
      if (activeTurn === abortController) activeTurn = null;
      return response;
    }

    const [applicationBranch, audioBranch] = response.body.tee();
    void consumeAssistantText(audioBranch, abortController).catch((error: unknown) => {
      if (abortController.signal.aborted) return;
      if (activeTurn === abortController) activeTurn = null;
      setVoiceSpeaking(false);
      setInlineStatus(error instanceof Error ? error.message : 'Live response audio failed.');
    });

    const headers = new Headers(response.headers);
    headers.delete('content-length');
    return new Response(filterLiveVoiceTextChunks(applicationBranch), {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  } catch (error) {
    if (activeTurn === abortController) activeTurn = null;
    throw error;
  }
}

export function shouldUseSmoothLiveVoiceAudio(input: RequestInfo | URL, init?: RequestInit): boolean {
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (method !== 'POST' || !isAutoSpeakEnabled() || !isLiveCallActive()) return false;
  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, window.location.origin);
  return CHAT_STREAM_PATH.test(url.pathname);
}

async function consumeAssistantText(
  stream: ReadableStream<Uint8Array>,
  turn: AbortController,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let responseText = '';
  try {
    while (!turn.signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const blocks = pending.split(/\n\n/);
      pending = blocks.pop() ?? '';
      for (const block of blocks) {
        const event = parseSseBlock(block);
        if (event?.type === 'text_chunk' && typeof event.text === 'string') {
          responseText = appendStreamText(responseText, event.text);
        }
      }
    }
    pending += decoder.decode();
    if (pending.trim()) {
      const event = parseSseBlock(pending);
      if (event?.type === 'text_chunk' && typeof event.text === 'string') {
        responseText = appendStreamText(responseText, event.text);
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (turn.signal.aborted || activeTurn !== turn) return;
  const spokenText = responseText.trim();
  if (!spokenText) {
    setInlineStatus('Live response finished without speakable text.');
    activeTurn = null;
    return;
  }

  const voiceResolution = resolvePlaybackVoiceWithDiagnostics('smooth-live-audio');
  const reporter = createLiveCallDiagnosticsReporter(voiceResolution.traceId);
  reporter.record('voice_resolution_decision', {
    ...voiceResolution.details,
    playback_voice_id: voiceResolution.voiceId,
    spoken_text_length: spokenText.length,
  }, 'voice-resolution');

  setInlineStatus('Generating and buffering smooth live audio…');
  try {
    await playBufferedTts(spokenText, {
      voiceId: voiceResolution.voiceId,
      signal: turn.signal,
      onStateChange: (state) => {
        reporter.record('buffered_playback_state', {
          caller: voiceResolution.diagnosticSource,
          playback_voice_id: voiceResolution.voiceId,
          playback_state: state,
        }, 'buffered-tts');
        if (activeTurn !== turn) return;
        if (state === 'buffering') {
          setVoiceSpeaking(false);
          setInlineStatus('Generating and buffering smooth live audio…');
        } else if (state === 'playing') {
          setVoiceSpeaking(true);
          setInlineStatus('Playing smooth live response audio…');
        } else if (state === 'finished') {
          setVoiceSpeaking(false);
          setInlineStatus('Live response audio finished.');
        }
      },
    });
    await reporter.close('buffered_playback_completed', {
      caller: voiceResolution.diagnosticSource,
      playback_voice_id: voiceResolution.voiceId,
    });
  } catch (error) {
    await reporter.close('buffered_playback_failed', {
      caller: voiceResolution.diagnosticSource,
      playback_voice_id: voiceResolution.voiceId,
      error_type: error instanceof Error ? error.name : typeof error,
      error_message: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
  if (activeTurn === turn) activeTurn = null;
}

export function filterLiveVoiceTextChunks(stream: ReadableStream<Uint8Array>): ReadableStream<Uint8Array> {
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
          if (pending.trim() && parseSseBlock(pending)?.type !== 'text_chunk') {
            controller.enqueue(encoder.encode(pending));
          }
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

export function appendStreamText(current: string, next: string): string {
  if (!current) return next;
  if (!next) return current;
  if (/\s$/.test(current) || /^\s/.test(next) || /^[,.;:!?\])}]/.test(next)) return `${current}${next}`;
  return `${current} ${next}`;
}

function stopLiveVoiceAudio(): void {
  activeTurn?.abort('live-audio-stopped');
  activeTurn = null;
  stopBufferedTtsPlayback();
  stopAssistantPcmStream(document);
  setVoiceSpeaking(false);
}

function isAutoSpeakEnabled(): boolean {
  return document.querySelector<HTMLInputElement>('.assistant-voice-toggle input[type="checkbox"]')?.checked ?? false;
}

function isLiveCallActive(): boolean {
  const card = document.querySelector<HTMLElement>('.assistant-live-card');
  if (!card) return false;
  if (card.dataset.liveVoiceStatus === 'connected') return true;
  return Array.from(card.querySelectorAll<HTMLButtonElement>('button')).some(
    (button) => button.textContent?.trim().toLowerCase() === 'end call',
  );
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
  window.dispatchEvent(new CustomEvent('omnix:assistant-audio-playback-state', {
    detail: { speaking, source: 'live-response' },
  }));
}

function setInlineStatus(message: string): void {
  const host = document.querySelector<HTMLElement>('.assistant-inline-status');
  if (!host) return;
  let status = host.querySelector<HTMLElement>('[data-omnix-live-voice-stream-status]');
  if (!status) {
    status = document.createElement('span');
    status.setAttribute('data-omnix-live-voice-stream-status', 'true');
    status.setAttribute('role', 'status');
    host.append(status);
  }
  status.textContent = message;
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

function connectAbortSignal(source: AbortSignal | null | undefined, target: AbortController): void {
  if (!source) return;
  if (source.aborted) {
    target.abort(source.reason);
    return;
  }
  source.addEventListener('abort', () => target.abort(source.reason), { once: true });
}
