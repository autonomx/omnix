import { createAssistantWorkspaceRuntimeConfig } from './runtime-config';

const STREAM_AUDIO_STATUS_ATTRIBUTE = 'data-omnix-stream-audio-status';
const STREAMING_TTS_SAMPLE_RATE = 24_000;
const STREAMING_TTS_START_BUFFER_SECONDS = 0.65;
const STREAMING_TTS_PLAYBACK_BLOCK_SECONDS = 0.25;
const STREAMING_TTS_SCHEDULE_LEAD_SECONDS = 0.08;
const STREAMING_TTS_URL = '/api/tts/stream/server-sent-events';

type StreamingAudioWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
};

type StreamingTtsEvent = {
  type?: string;
  message?: string;
  audio_b64?: string;
  sample_rate?: number;
};

type MessageStreamPlayback = {
  button: HTMLButtonElement;
  audioContext: AudioContext;
  abortController: AbortController;
  sources: Set<AudioBufferSourceNode>;
  pendingPcm: Int16Array[];
  pendingSamples: number;
  sampleRate: number;
  nextStartAt: number;
  started: boolean;
  serverDone: boolean;
  closed: boolean;
};

let activePlayback: MessageStreamPlayback | null = null;

export function isAssistantPcmStreamActive(button: HTMLButtonElement): boolean {
  return activePlayback?.button === button;
}

export async function startAssistantPcmStream(
  root: ParentNode,
  button: HTMLButtonElement,
  text: string,
): Promise<void> {
  const liveWindow = window as StreamingAudioWindow;
  const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
  if (!AudioContextCtor || typeof window.fetch !== 'function' || typeof window.ReadableStream === 'undefined') {
    setStreamAudioStatus(root, 'Streaming audio requires browser streaming fetch and AudioContext support.');
    return;
  }

  stopAssistantPcmStream(root);
  const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });
  const playback: MessageStreamPlayback = {
    button,
    audioContext,
    abortController: new AbortController(),
    sources: new Set<AudioBufferSourceNode>(),
    pendingPcm: [],
    pendingSamples: 0,
    sampleRate: STREAMING_TTS_SAMPLE_RATE,
    nextStartAt: audioContext.currentTime + STREAMING_TTS_SCHEDULE_LEAD_SECONDS,
    started: false,
    serverDone: false,
    closed: false,
  };
  activePlayback = playback;
  setButtonStreaming(button, true);
  setStreamAudioStatus(root, 'Buffering streaming response audio…');

  try {
    if (audioContext.state !== 'running') await audioContext.resume();
    const response = await fetch(STREAMING_TTS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        speaker: selectedVoiceId(),
        language: 'English',
        chunk_size: 12,
        temperature: 0.6,
        top_k: 20,
        top_p: 0.85,
        repetition_penalty: 1.0,
        append_silence: false,
        max_new_tokens: 180,
        non_streaming_mode: false,
        parity_mode: true,
      }),
      signal: playback.abortController.signal,
    });
    if (!response.ok || !response.body) throw new Error(`Streaming TTS SSE failed with status ${response.status}.`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';

    while (!playback.closed) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split(/\r?\n\r?\n/);
      pending = events.pop() ?? '';

      for (const eventText of events) {
        const message = parseStreamingTtsSseEvent(eventText);
        if (!message) continue;
        if (message.type === 'error') throw new Error(message.message || 'Streaming TTS failed.');
        if (message.type === 'done') {
          markServerDone(root, playback);
          return;
        }
        if (message.type !== 'chunk' || typeof message.audio_b64 !== 'string') continue;
        enqueuePcmChunk(root, playback, message);
      }
    }

    markServerDone(root, playback);
  } catch (error) {
    if (playback.closed || activePlayback !== playback || isAbortError(error)) return;
    terminatePlayback(playback);
    if (activePlayback === playback) activePlayback = null;
    setButtonStreaming(button, false);
    setStreamAudioStatus(root, error instanceof Error ? error.message : 'Streaming response audio failed.');
  }
}

export function stopAssistantPcmStream(root: ParentNode, status?: string): void {
  const playback = activePlayback;
  activePlayback = null;
  if (!playback) return;
  terminatePlayback(playback);
  setButtonStreaming(playback.button, false);
  if (status) setStreamAudioStatus(root, status);
}

function enqueuePcmChunk(root: ParentNode, playback: MessageStreamPlayback, message: StreamingTtsEvent): void {
  if (playback.closed || typeof message.audio_b64 !== 'string') return;
  const samples = base64ToPcm16(message.audio_b64);
  if (!samples.length) return;

  const sampleRate = typeof message.sample_rate === 'number' && message.sample_rate > 0
    ? message.sample_rate
    : STREAMING_TTS_SAMPLE_RATE;
  if (playback.pendingSamples > 0 && sampleRate !== playback.sampleRate) flushBufferedPcm(root, playback, true);
  playback.sampleRate = sampleRate;
  playback.pendingPcm.push(samples);
  playback.pendingSamples += samples.length;
  flushBufferedPcm(root, playback, false);
}

function flushBufferedPcm(root: ParentNode, playback: MessageStreamPlayback, force: boolean): void {
  if (playback.closed || playback.pendingSamples === 0) return;
  const startBufferSamples = Math.max(1, Math.round(playback.sampleRate * STREAMING_TTS_START_BUFFER_SECONDS));
  const playbackBlockSamples = Math.max(1, Math.round(playback.sampleRate * STREAMING_TTS_PLAYBACK_BLOCK_SECONDS));

  if (!playback.started) {
    if (!force && playback.pendingSamples < startBufferSamples) return;
    playback.started = true;
    schedulePcmSamples(root, playback, takeBufferedPcm(playback, playback.pendingSamples));
    setStreamAudioStatus(root, 'Streaming response audio…');
    return;
  }

  while (playback.pendingSamples >= playbackBlockSamples || (force && playback.pendingSamples > 0)) {
    const sampleCount = force ? playback.pendingSamples : playbackBlockSamples;
    schedulePcmSamples(root, playback, takeBufferedPcm(playback, sampleCount));
  }
}

function takeBufferedPcm(playback: MessageStreamPlayback, sampleCount: number): Int16Array {
  const output = new Int16Array(sampleCount);
  let written = 0;
  while (written < sampleCount && playback.pendingPcm.length > 0) {
    const chunk = playback.pendingPcm[0];
    const take = Math.min(chunk.length, sampleCount - written);
    output.set(chunk.subarray(0, take), written);
    written += take;
    if (take === chunk.length) playback.pendingPcm.shift();
    else playback.pendingPcm[0] = chunk.slice(take);
  }
  playback.pendingSamples = Math.max(0, playback.pendingSamples - written);
  return written === output.length ? output : output.slice(0, written);
}

function schedulePcmSamples(root: ParentNode, playback: MessageStreamPlayback, samples: Int16Array): void {
  if (playback.closed || samples.length === 0) return;
  const audioBuffer = pcm16ToAudioBuffer(playback.audioContext, samples, playback.sampleRate);
  const source = playback.audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playback.audioContext.destination);

  const startAt = Math.max(
    playback.nextStartAt,
    playback.audioContext.currentTime + STREAMING_TTS_SCHEDULE_LEAD_SECONDS,
  );
  source.start(startAt);
  playback.nextStartAt = startAt + audioBuffer.duration;
  playback.sources.add(source);
  source.addEventListener('ended', () => {
    playback.sources.delete(source);
    try { source.disconnect(); } catch { /* ignore browser cleanup failures */ }
    if (playback.serverDone && playback.pendingSamples === 0 && playback.sources.size === 0) finishPlayback(root, playback);
  }, { once: true });
}

function markServerDone(root: ParentNode, playback: MessageStreamPlayback): void {
  playback.serverDone = true;
  flushBufferedPcm(root, playback, true);
  if (playback.pendingSamples === 0 && playback.sources.size === 0) finishPlayback(root, playback);
}

function finishPlayback(root: ParentNode, playback: MessageStreamPlayback): void {
  if (playback.closed) return;
  playback.closed = true;
  if (activePlayback === playback) activePlayback = null;
  setButtonStreaming(playback.button, false);
  void playback.audioContext.close().catch(() => undefined);
  setStreamAudioStatus(root, 'Streaming response audio finished.');
}

function terminatePlayback(playback: MessageStreamPlayback): void {
  if (playback.closed) return;
  playback.closed = true;
  try { playback.abortController.abort(); } catch { /* ignore browser cleanup failures */ }
  playback.sources.forEach((source) => {
    try { source.stop(); } catch { /* ignore browser cleanup failures */ }
    try { source.disconnect(); } catch { /* ignore browser cleanup failures */ }
  });
  playback.sources.clear();
  playback.pendingPcm = [];
  playback.pendingSamples = 0;
  void playback.audioContext.close().catch(() => undefined);
}

function setButtonStreaming(button: HTMLButtonElement, streaming: boolean): void {
  button.textContent = streaming ? '■' : '≋';
  button.title = streaming ? 'Stop streaming response audio' : 'Stream response audio';
  button.setAttribute('aria-label', streaming ? 'Stop streaming response audio' : 'Stream response audio');
  button.setAttribute('aria-pressed', streaming ? 'true' : 'false');
}

function setStreamAudioStatus(root: ParentNode, message: string): void {
  const host = root.querySelector<HTMLElement>('.assistant-inline-status');
  if (!host) return;
  let status = host.querySelector<HTMLElement>(`[${STREAM_AUDIO_STATUS_ATTRIBUTE}]`);
  if (!status) {
    status = document.createElement('span');
    status.setAttribute(STREAM_AUDIO_STATUS_ATTRIBUTE, 'true');
    status.setAttribute('role', 'status');
    host.appendChild(status);
  }
  status.textContent = message;
}

function selectedVoiceId(): string | null {
  const selected = document.querySelector<HTMLSelectElement>('select[aria-label="Cloned voice"]')?.value.trim();
  if (selected) return selected;
  return createAssistantWorkspaceRuntimeConfig().ttsVoice?.trim() || null;
}

function parseStreamingTtsSseEvent(value: string): StreamingTtsEvent | null {
  const data = value
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n');
  if (!data) return null;
  try { return JSON.parse(data) as StreamingTtsEvent; } catch { return null; }
}

function base64ToPcm16(value: string): Int16Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length - (binary.length % 2));
  for (let index = 0; index < bytes.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Int16Array(bytes.buffer);
}

function pcm16ToAudioBuffer(audioContext: AudioContext, input: Int16Array, sampleRate: number): AudioBuffer {
  const buffer = audioContext.createBuffer(1, input.length, sampleRate);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < input.length; index += 1) channel[index] = input[index] / 32768;
  return buffer;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
