import {
  isAssistantPcmStreamActive,
  startAssistantPcmStream,
  stopAssistantPcmStream,
} from './assistant-pcm-stream-websocket-player';

const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/[^/]+\/messages\/stream$/;
const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const LIVE_VOICE_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const VOICE_SETTINGS_KEY = 'omnix.chatbot.assistantSettings';
const MIN_SENTENCE_CHARS = 36;
const MAX_PHRASE_CHARS = 120;
const PLAYBACK_POLL_MS = 25;
const PLAYBACK_TIMEOUT_MS = 120_000;

type ChatStreamEvent = {
  type?: string;
  text?: string;
};

type LiveVoiceWindow = Window & typeof globalThis & {
  __omnixLiveVoiceUnifiedAudioInstalled?: boolean;
};

let originalFetch: typeof window.fetch | null = null;
let playbackGeneration = 0;
let speechQueue: Promise<void> = Promise.resolve();
let bridgeButton: HTMLButtonElement | null = null;
let hiddenVoiceSelect: HTMLSelectElement | null = null;

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

  return () => {
    if (originalFetch) window.fetch = originalFetch;
    originalFetch = null;
    window.removeEventListener(LIVE_VOICE_INTERRUPT_EVENT, stopLiveVoiceUnifiedAudio);
    window.removeEventListener(LIVE_VOICE_STOP_EVENT, stopLiveVoiceUnifiedAudio);
    window.removeEventListener('beforeunload', stopLiveVoiceUnifiedAudio);
    stopLiveVoiceUnifiedAudio();
    hiddenVoiceSelect?.remove();
    hiddenVoiceSelect = null;
    liveWindow.__omnixLiveVoiceUnifiedAudioInstalled = false;
  };
}

async function interceptLiveVoiceFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  const response = await fetchImpl(input, init);
  if (!shouldUseUnifiedLiveVoiceAudio(input, init) || !response.body || !response.ok) return response;

  stopAssistantPcmStream(document);
  const [applicationBranch, audioBranch] = response.body.tee();
  const generation = ++playbackGeneration;
  speechQueue = Promise.resolve();
  void consumeLiveVoiceText(audioBranch, generation).catch((error: unknown) => {
    if (generation !== playbackGeneration) return;
    setInlineStatus(error instanceof Error ? error.message : 'Live voice audio streaming failed.');
    setVoiceSpeaking(false);
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
  return CHAT_STREAM_PATH.test(url.pathname) && isLiveVoiceActive() && isAutoSpeakEnabled();
}

function isLiveVoiceActive(): boolean {
  const card = document.querySelector<HTMLElement>('.assistant-live-card');
  if (!card) return false;
  if (card.dataset.liveVoiceStatus === 'connected') return true;
  return Array.from(card.querySelectorAll<HTMLButtonElement>('button')).some(
    (button) => button.textContent?.trim().toLowerCase() === 'end call',
  );
}

function isAutoSpeakEnabled(): boolean {
  return document.querySelector<HTMLInputElement>('.assistant-voice-toggle input[type="checkbox"]')?.checked ?? false;
}

async function consumeLiveVoiceText(stream: ReadableStream<Uint8Array>, generation: number): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let phrase = '';

  while (generation === playbackGeneration) {
    const { value, done } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    const blocks = pending.split(/\n\n/);
    pending = blocks.pop() ?? '';
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event?.type !== 'text_chunk' || typeof event.text !== 'string') continue;
      phrase = mergeText(phrase, event.text);
      if (shouldFlushPhrase(phrase)) {
        queuePhrase(phrase, generation);
        phrase = '';
      }
    }
  }

  pending += decoder.decode();
  if (pending.trim()) {
    const event = parseSseBlock(pending);
    if (event?.type === 'text_chunk' && typeof event.text === 'string') phrase = mergeText(phrase, event.text);
  }
  if (phrase.trim()) queuePhrase(phrase, generation);
  await speechQueue;
  if (generation === playbackGeneration) setVoiceSpeaking(false);
}

function queuePhrase(text: string, generation: number): void {
  const phrase = text.trim();
  if (!phrase) return;
  speechQueue = speechQueue.catch(() => undefined).then(async () => {
    if (generation !== playbackGeneration) return;
    await playPhrase(phrase, generation);
  });
}

async function playPhrase(text: string, generation: number): Promise<void> {
  ensureVoiceSelectionBridge();
  bridgeButton ??= document.createElement('button');
  setVoiceSpeaking(true);
  setInlineStatus('Buffering live response audio…');
  await startAssistantPcmStream(document, bridgeButton, text);

  const startedAt = performance.now();
  while (generation === playbackGeneration && isAssistantPcmStreamActive(bridgeButton)) {
    if (performance.now() - startedAt > PLAYBACK_TIMEOUT_MS) {
      stopAssistantPcmStream(document, 'Live response audio timed out.');
      throw new Error('Live response audio timed out.');
    }
    await new Promise((resolve) => window.setTimeout(resolve, PLAYBACK_POLL_MS));
  }
}

function stopLiveVoiceUnifiedAudio(): void {
  playbackGeneration += 1;
  speechQueue = Promise.resolve();
  stopAssistantPcmStream(document);
  setVoiceSpeaking(false);
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

function ensureVoiceSelectionBridge(): void {
  const existing = document.querySelector<HTMLSelectElement>('select[aria-label="Cloned voice"]');
  if (existing) return;
  const voiceId = readStoredVoiceId();
  if (!voiceId) return;
  hiddenVoiceSelect ??= document.createElement('select');
  hiddenVoiceSelect.hidden = true;
  hiddenVoiceSelect.setAttribute('aria-label', 'Cloned voice');
  hiddenVoiceSelect.setAttribute('data-omnix-live-voice-bridge', 'true');
  hiddenVoiceSelect.replaceChildren(new Option(voiceId, voiceId, true, true));
  if (!hiddenVoiceSelect.isConnected) document.body.appendChild(hiddenVoiceSelect);
}

function readStoredVoiceId(): string {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(VOICE_SETTINGS_KEY) || '{}') as { voiceId?: unknown };
    return typeof parsed.voiceId === 'string' ? parsed.voiceId.trim() : '';
  } catch {
    return '';
  }
}
