import { createAssistantWorkspaceRuntimeConfig } from './runtime-config';

const STREAM_AUDIO_BUTTON_ATTRIBUTE = 'data-omnix-stream-audio';
const STREAM_AUDIO_STATUS_ATTRIBUTE = 'data-omnix-stream-audio-status';
const STREAMING_TTS_SAMPLE_RATE = 24_000;
const STREAMING_TTS_START_DELAY_SECONDS = 0.03;
const STREAMING_TTS_URL = '/api/tts/stream/server-sent-events';
const installedRoots = new WeakSet<ParentNode>();

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
  nextStartAt: number;
  serverDone: boolean;
  closed: boolean;
};

let activePlayback: MessageStreamPlayback | null = null;

export function initializeChatMessageStreamAudioController(root: ParentNode = document): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined' || installedRoots.has(root)) return () => undefined;
  installedRoots.add(root);

  injectStreamAudioButtons(root);
  const eventTarget = root instanceof Document ? root : root.ownerDocument ?? document;
  const observerTarget = root instanceof Document ? root.documentElement : root as Node;
  const observer = new MutationObserver(() => injectStreamAudioButtons(root));
  observer.observe(observerTarget, { childList: true, subtree: true });

  const handleClick = (event: Event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>(`button[${STREAM_AUDIO_BUTTON_ATTRIBUTE}]`);
    if (!button || !rootContains(root, button)) return;

    event.preventDefault();
    if (activePlayback?.button === button) {
      stopActivePlayback(root, 'Streaming response audio stopped.');
      return;
    }

    const message = button.closest<HTMLElement>('.assistant-chat-message.assistant');
    const text = message?.querySelector<HTMLElement>('.assistant-chat-bubble > p')?.textContent?.trim() ?? '';
    if (!text) {
      setStreamAudioStatus(root, 'No assistant response is ready to stream.');
      return;
    }

    stopActivePlayback(root);
    void streamMessageAudio(root, button, text);
  };

  eventTarget.addEventListener('click', handleClick, true);
  return () => {
    observer.disconnect();
    eventTarget.removeEventListener('click', handleClick, true);
    if (activePlayback && rootContains(root, activePlayback.button)) stopActivePlayback(root);
    installedRoots.delete(root);
  };
}

export function injectStreamAudioButtons(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>('.assistant-chat-message.assistant .assistant-message-actions').forEach((actions) => {
    if (actions.querySelector(`[${STREAM_AUDIO_BUTTON_ATTRIBUTE}]`)) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '≋';
    button.title = 'Stream response audio';
    button.setAttribute('aria-label', 'Stream response audio');
    button.setAttribute(STREAM_AUDIO_BUTTON_ATTRIBUTE, 'true');

    const moreButton = actions.querySelector<HTMLButtonElement>('button[aria-label="More response actions"]');
    actions.insertBefore(button, moreButton ?? null);
  });
}

async function streamMessageAudio(root: ParentNode, button: HTMLButtonElement, text: string): Promise<void> {
  const liveWindow = window as StreamingAudioWindow;
  const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
  if (!AudioContextCtor || typeof window.fetch !== 'function' || typeof window.ReadableStream === 'undefined') {
    setStreamAudioStatus(root, 'Streaming audio requires browser streaming fetch and AudioContext support.');
    return;
  }

  const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });
  const playback: MessageStreamPlayback = {
    button,
    audioContext,
    abortController: new AbortController(),
    sources: new Set<AudioBufferSourceNode>(),
    nextStartAt: audioContext.currentTime + STREAMING_TTS_START_DELAY_SECONDS,
    serverDone: false,
    closed: false,
  };
  activePlayback = playback;
  setButtonStreaming(button, true);
  setStreamAudioStatus(root, 'Connecting streaming response audio…');

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
    let firstChunkScheduled = false;

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

        schedulePcmChunk(root, playback, message);
        if (!firstChunkScheduled) {
          firstChunkScheduled = true;
          setStreamAudioStatus(root, 'Streaming response audio…');
        }
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

function schedulePcmChunk(root: ParentNode, playback: MessageStreamPlayback, message: StreamingTtsEvent): void {
  if (playback.closed || typeof message.audio_b64 !== 'string') return;
  const pcm = base64ToArrayBuffer(message.audio_b64);
  if (!pcm.byteLength) return;

  const sampleRate = typeof message.sample_rate === 'number' && message.sample_rate > 0
    ? message.sample_rate
    : STREAMING_TTS_SAMPLE_RATE;
  const audioBuffer = pcm16ArrayBufferToAudioBuffer(playback.audioContext, pcm, sampleRate);
  const source = playback.audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playback.audioContext.destination);
  const startAt = Math.max(playback.nextStartAt, playback.audioContext.currentTime + 0.01);
  source.start(startAt);
  playback.nextStartAt = startAt + audioBuffer.duration;
  playback.sources.add(source);
  source.addEventListener('ended', () => {
    playback.sources.delete(source);
    try { source.disconnect(); } catch { /* ignore browser cleanup failures */ }
    if (playback.serverDone && playback.sources.size === 0) finishPlayback(root, playback);
  }, { once: true });
}

function markServerDone(root: ParentNode, playback: MessageStreamPlayback): void {
  playback.serverDone = true;
  if (playback.sources.size === 0) finishPlayback(root, playback);
}

function finishPlayback(root: ParentNode, playback: MessageStreamPlayback): void {
  if (playback.closed) return;
  playback.closed = true;
  if (activePlayback === playback) activePlayback = null;
  setButtonStreaming(playback.button, false);
  void playback.audioContext.close().catch(() => undefined);
  setStreamAudioStatus(root, 'Streaming response audio finished.');
}

function stopActivePlayback(root: ParentNode, status?: string): void {
  const playback = activePlayback;
  activePlayback = null;
  if (!playback) return;
  terminatePlayback(playback);
  setButtonStreaming(playback.button, false);
  if (status) setStreamAudioStatus(root, status);
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

function base64ToArrayBuffer(value: string): ArrayBuffer {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

function pcm16ArrayBufferToAudioBuffer(audioContext: AudioContext, pcm: ArrayBuffer, sampleRate: number): AudioBuffer {
  const input = new Int16Array(pcm);
  const buffer = audioContext.createBuffer(1, input.length, sampleRate);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < input.length; index += 1) channel[index] = input[index] / 32768;
  return buffer;
}

function rootContains(root: ParentNode, element: Element): boolean {
  return root instanceof Document ? root.documentElement.contains(element) : (root as Node).contains(element);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
