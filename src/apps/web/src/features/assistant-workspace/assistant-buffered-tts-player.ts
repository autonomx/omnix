const DEFAULT_SAMPLE_RATE = 24_000;
const STREAMING_TTS_WEBSOCKET_PATH = '/api/tts/stream/websocket';
const STREAMING_TTS_SSE_PATH = '/api/tts/stream/server-sent-events';
const AVATAR_PCM_EVENT = 'omnix:character-avatar-pcm';
const PLAYBACK_LEAD_SECONDS = 0.08;

export type BufferedTtsPlaybackState = 'buffering' | 'playing' | 'finished' | 'stopped';

export type BufferedTtsPlaybackOptions = {
  voiceId?: string | null;
  signal?: AbortSignal | null;
  onStateChange?: (state: BufferedTtsPlaybackState) => void;
};

type PcmSynthesisResult = {
  sampleRate: number;
  samples: Int16Array;
};

type StreamingAudioWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
  WebSocket?: typeof WebSocket;
};

type TtsControlEvent = {
  type?: string;
  message?: string;
  sample_rate?: number;
};

type ActivePlayback = {
  abortController: AbortController;
  audioContext: AudioContext;
  source: AudioBufferSourceNode | null;
  state: BufferedTtsPlaybackState;
};

let activePlayback: ActivePlayback | null = null;

export function stopBufferedTtsPlayback(): void {
  const playback = activePlayback;
  activePlayback = null;
  if (!playback) return;
  playback.state = 'stopped';
  playback.abortController.abort('playback-stopped');
  try { playback.source?.stop(); } catch { /* source may already be stopped */ }
  try { playback.source?.disconnect(); } catch { /* ignore cleanup failures */ }
  void playback.audioContext.close().catch(() => undefined);
}

export async function playBufferedTts(
  text: string,
  options: BufferedTtsPlaybackOptions = {},
): Promise<void> {
  const spokenText = text.trim();
  if (!spokenText) throw new Error('No assistant response is ready to play.');

  stopBufferedTtsPlayback();
  const liveWindow = window as StreamingAudioWindow;
  const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
  if (!AudioContextCtor) throw new Error('Response audio requires browser AudioContext support.');

  const audioContext = new AudioContextCtor({ latencyHint: 'playback', sampleRate: DEFAULT_SAMPLE_RATE });
  const abortController = new AbortController();
  connectAbortSignal(options.signal, abortController);
  const playback: ActivePlayback = {
    abortController,
    audioContext,
    source: null,
    state: 'buffering',
  };
  activePlayback = playback;
  options.onStateChange?.('buffering');

  try {
    if (audioContext.state !== 'running') await audioContext.resume();
    if (abortController.signal.aborted) throw abortError();

    const result = await synthesizePcm(spokenText, options.voiceId ?? null, abortController.signal);
    if (!result.samples.length) throw new Error('TTS returned no playable audio.');
    if (abortController.signal.aborted || activePlayback !== playback) throw abortError();

    const audioBuffer = pcm16ToAudioBuffer(audioContext, result.samples, result.sampleRate);
    const source = audioContext.createBufferSource();
    playback.source = source;
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    const startAt = audioContext.currentTime + PLAYBACK_LEAD_SECONDS;
    const startDelayMs = Math.max(0, (startAt - audioContext.currentTime) * 1000);
    const ended = new Promise<void>((resolve) => {
      source.addEventListener('ended', () => resolve(), { once: true });
    });

    window.setTimeout(() => {
      if (abortController.signal.aborted || activePlayback !== playback) return;
      playback.state = 'playing';
      options.onStateChange?.('playing');
      window.dispatchEvent(new CustomEvent(AVATAR_PCM_EVENT, {
        detail: {
          samples: result.samples.slice(),
          sampleRate: result.sampleRate,
        },
      }));
    }, startDelayMs);

    source.start(startAt);
    await ended;
    if (abortController.signal.aborted || activePlayback !== playback) return;
    playback.state = 'finished';
    options.onStateChange?.('finished');
  } finally {
    if (activePlayback === playback) activePlayback = null;
    try { playback.source?.disconnect(); } catch { /* ignore cleanup failures */ }
    if (audioContext.state !== 'closed') await audioContext.close().catch(() => undefined);
  }
}

async function synthesizePcm(
  text: string,
  voiceId: string | null,
  signal: AbortSignal,
): Promise<PcmSynthesisResult> {
  try {
    return await synthesizePcmWebSocket(text, voiceId, signal);
  } catch (error) {
    if (signal.aborted) throw abortError();
    console.info('[Omnix Audio] WebSocket TTS unavailable; falling back to SSE.', {
      reason: error instanceof Error ? error.message : String(error),
    });
    return synthesizePcmSse(text, voiceId, signal);
  }
}

function synthesizePcmWebSocket(
  text: string,
  voiceId: string | null,
  signal: AbortSignal,
): Promise<PcmSynthesisResult> {
  const liveWindow = window as StreamingAudioWindow;
  const WebSocketCtor = liveWindow.WebSocket;
  if (!WebSocketCtor) return Promise.reject(new Error('Streaming TTS requires WebSocket support.'));

  return new Promise((resolve, reject) => {
    const url = new URL(STREAMING_TTS_WEBSOCKET_PATH, window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocketCtor(url.toString());
    socket.binaryType = 'arraybuffer';
    const chunks: Int16Array[] = [];
    let sampleRate = DEFAULT_SAMPLE_RATE;
    let settled = false;

    const cleanup = () => {
      signal.removeEventListener('abort', handleAbort);
      try { socket.close(1000, 'complete'); } catch { /* ignore close failures */ }
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    };
    const complete = () => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve({ sampleRate, samples: mergePcmChunks(chunks) });
    };
    const handleAbort = () => fail(abortError());
    signal.addEventListener('abort', handleAbort, { once: true });

    socket.addEventListener('open', () => {
      if (signal.aborted) {
        handleAbort();
        return;
      }
      socket.send(JSON.stringify({
        text,
        speaker: voiceId,
        language: 'English',
        chunk_size: 8,
        temperature: 0.6,
        top_k: 20,
        top_p: 0.85,
        repetition_penalty: 1,
        append_silence: false,
        non_streaming_mode: false,
        parity_mode: true,
        diagnostics_stream_id: createRequestId('chat-audio'),
      }));
    }, { once: true });

    socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (settled) return;
      if (event.data instanceof ArrayBuffer) {
        const evenBytes = event.data.byteLength - (event.data.byteLength % 2);
        if (evenBytes > 0) chunks.push(new Int16Array(event.data.slice(0, evenBytes)));
        return;
      }
      const message = parseControlEvent(event.data);
      if (!message) return;
      if ((message.type === 'start' || message.type === 'format') && Number(message.sample_rate) > 0) {
        sampleRate = Number(message.sample_rate);
        return;
      }
      if (message.type === 'error') {
        fail(new Error(message.message || 'Streaming TTS failed.'));
        return;
      }
      if (message.type === 'done') complete();
    });
    socket.addEventListener('error', () => fail(new Error('Streaming TTS connection failed.')));
    socket.addEventListener('close', () => {
      if (!settled) fail(new Error('Streaming TTS connection closed before audio completed.'));
    });
  });
}

async function synthesizePcmSse(
  text: string,
  voiceId: string | null,
  signal: AbortSignal,
): Promise<PcmSynthesisResult> {
  const response = await fetch(STREAMING_TTS_SSE_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      speaker: voiceId,
      language: 'English',
      chunk_size: 8,
      temperature: 0.6,
      top_k: 20,
      top_p: 0.85,
      repetition_penalty: 1,
      append_silence: false,
      max_new_tokens: 320,
      non_streaming_mode: false,
      parity_mode: true,
      request_id: createRequestId('chat-audio-sse'),
    }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`Streaming TTS failed with status ${response.status}.`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const chunks: Int16Array[] = [];
  let sampleRate = DEFAULT_SAMPLE_RATE;
  let pending = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const blocks = pending.split(/\n\n/);
      pending = blocks.pop() ?? '';
      for (const block of blocks) {
        const message = parseSseEvent(block);
        if (!message) continue;
        if (message.type === 'error') throw new Error(String(message.message || 'Streaming TTS failed.'));
        if (message.type !== 'chunk' || typeof message.audio_b64 !== 'string') continue;
        sampleRate = Number(message.sample_rate) > 0 ? Number(message.sample_rate) : sampleRate;
        const samples = base64Pcm16(message.audio_b64);
        if (samples.length) chunks.push(samples);
      }
    }
  } finally {
    reader.releaseLock();
  }
  return { sampleRate, samples: mergePcmChunks(chunks) };
}

export function mergePcmChunks(chunks: readonly Int16Array[]): Int16Array {
  const totalLength = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const merged = new Int16Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function pcm16ToAudioBuffer(
  audioContext: AudioContext,
  samples: Int16Array,
  sourceSampleRate: number,
): AudioBuffer {
  const targetRate = audioContext.sampleRate;
  const outputLength = sourceSampleRate === targetRate
    ? samples.length
    : Math.max(1, Math.round(samples.length * targetRate / sourceSampleRate));
  const audioBuffer = audioContext.createBuffer(1, outputLength, targetRate);
  const channel = audioBuffer.getChannelData(0);
  if (sourceSampleRate === targetRate) {
    for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 32768;
    return audioBuffer;
  }
  const sourceStep = sourceSampleRate / targetRate;
  for (let index = 0; index < outputLength; index += 1) {
    const sourcePosition = Math.min(samples.length - 1, index * sourceStep);
    const left = Math.floor(sourcePosition);
    const right = Math.min(samples.length - 1, left + 1);
    const fraction = sourcePosition - left;
    channel[index] = ((samples[left] * (1 - fraction)) + (samples[right] * fraction)) / 32768;
  }
  return audioBuffer;
}

function base64Pcm16(value: string): Int16Array {
  try {
    const binary = window.atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    const evenBytes = bytes.byteLength - (bytes.byteLength % 2);
    return evenBytes ? new Int16Array(bytes.buffer.slice(0, evenBytes)) : new Int16Array();
  } catch {
    return new Int16Array();
  }
}

function parseControlEvent(value: string): TtsControlEvent | null {
  try { return JSON.parse(value) as TtsControlEvent; } catch { return null; }
}

function parseSseEvent(block: string): Record<string, unknown> | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return null;
  try { return JSON.parse(data) as Record<string, unknown>; } catch { return null; }
}

function createRequestId(prefix: string): string {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function connectAbortSignal(source: AbortSignal | null | undefined, target: AbortController): void {
  if (!source) return;
  if (source.aborted) {
    target.abort(source.reason);
    return;
  }
  source.addEventListener('abort', () => target.abort(source.reason), { once: true });
}

function abortError(): Error {
  return new DOMException('Audio playback was stopped.', 'AbortError');
}
