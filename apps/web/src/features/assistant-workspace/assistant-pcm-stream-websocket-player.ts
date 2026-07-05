import { createAssistantWorkspaceRuntimeConfig } from './runtime-config';

const STREAM_AUDIO_STATUS_ATTRIBUTE = 'data-omnix-stream-audio-status';
const STREAMING_TTS_SAMPLE_RATE = 24_000;
const STREAMING_TTS_START_BUFFER_SECONDS = 2.0;
const STREAMING_TTS_REBUFFER_SECONDS = 1.5;
const STREAMING_TTS_MAX_REBUFFER_SECONDS = 3.0;
const STREAMING_TTS_TRANSITION_FADE_SECONDS = 0.008;
const STREAMING_TTS_WEBSOCKET_PATH = '/api/tts/stream/websocket';
const STREAMING_TTS_CHUNK_SIZE = 8;
const STREAMING_TTS_WORKLET_NAME = 'omnix-assistant-pcm-stream';

type StreamingAudioWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
  AudioWorkletNode?: typeof AudioWorkletNode;
  WebSocket?: typeof WebSocket;
};

type StreamingTtsControlEvent = {
  type?: string;
  message?: string;
  sample_rate?: number;
};

type WorkletStatusEvent = {
  type?: string;
  buffered_samples?: number;
};

type MessageStreamPlayback = {
  button: HTMLButtonElement;
  audioContext: AudioContext;
  node: AudioWorkletNode | null;
  socket: WebSocket | null;
  sampleRate: number;
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
  const AudioWorkletNodeCtor = liveWindow.AudioWorkletNode;
  const WebSocketCtor = liveWindow.WebSocket;
  if (!AudioContextCtor || !AudioWorkletNodeCtor || !WebSocketCtor) {
    setStreamAudioStatus(root, 'Streaming audio requires browser AudioWorklet and WebSocket support.');
    return;
  }

  stopAssistantPcmStream(root);
  const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });
  const playback: MessageStreamPlayback = {
    button,
    audioContext,
    node: null,
    socket: null,
    sampleRate: STREAMING_TTS_SAMPLE_RATE,
    serverDone: false,
    closed: false,
  };
  activePlayback = playback;
  setButtonStreaming(button, true);
  setStreamAudioStatus(root, 'Buffering streaming response audio…');

  try {
    if (audioContext.state !== 'running') await audioContext.resume();
    playback.node = await createContinuousPcmSink(root, playback, AudioWorkletNodeCtor);
    if (playback.closed || activePlayback !== playback) return;
    await streamPcmWebSocket(playback, WebSocketCtor, text);
  } catch (error) {
    if (playback.closed || activePlayback !== playback) return;
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

function streamPcmWebSocket(
  playback: MessageStreamPlayback,
  WebSocketCtor: typeof WebSocket,
  text: string,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocketCtor(streamingTtsWebSocketUrl());
    playback.socket = socket;
    socket.binaryType = 'arraybuffer';

    socket.addEventListener('open', () => {
      if (playback.closed) {
        socket.close();
        return;
      }
      socket.send(JSON.stringify({
        text,
        speaker: selectedVoiceId(),
        language: 'English',
        chunk_size: STREAMING_TTS_CHUNK_SIZE,
        temperature: 0.6,
        top_k: 20,
        top_p: 0.85,
        repetition_penalty: 1.0,
        append_silence: false,
        non_streaming_mode: false,
        parity_mode: true,
      }));
    }, { once: true });

    socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (playback.closed) return;
      if (event.data instanceof ArrayBuffer) {
        enqueuePcmBytes(playback, event.data);
        return;
      }
      if (typeof event.data !== 'string') return;
      const message = parseStreamingTtsControlEvent(event.data);
      if (!message) return;
      if (message.type === 'start' || message.type === 'format') {
        if (typeof message.sample_rate === 'number' && message.sample_rate > 0) {
          playback.sampleRate = message.sample_rate;
        }
        return;
      }
      if (message.type === 'error') {
        reject(new Error(message.message || 'Streaming TTS failed.'));
        return;
      }
      if (message.type === 'done') {
        markServerDone(playback);
        resolve();
      }
    });

    socket.addEventListener('error', () => {
      if (!playback.closed && !playback.serverDone) reject(new Error('Streaming TTS connection failed.'));
    });
    socket.addEventListener('close', () => {
      if (!playback.closed && !playback.serverDone) reject(new Error('Streaming TTS connection closed before completion.'));
    });
  });
}

async function createContinuousPcmSink(
  root: ParentNode,
  playback: MessageStreamPlayback,
  AudioWorkletNodeCtor: typeof AudioWorkletNode,
): Promise<AudioWorkletNode> {
  const moduleUrl = createAudioWorkletModuleUrl();
  try {
    await playback.audioContext.audioWorklet.addModule(moduleUrl.url);
  } finally {
    moduleUrl.revoke();
  }

  const node = new AudioWorkletNodeCtor(playback.audioContext, STREAMING_TTS_WORKLET_NAME, {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: {
      startBufferSamples: Math.round(playback.audioContext.sampleRate * STREAMING_TTS_START_BUFFER_SECONDS),
      rebufferSamples: Math.round(playback.audioContext.sampleRate * STREAMING_TTS_REBUFFER_SECONDS),
      maxRebufferSamples: Math.round(
        playback.audioContext.sampleRate * STREAMING_TTS_MAX_REBUFFER_SECONDS,
      ),
      transitionFadeSamples: Math.round(
        playback.audioContext.sampleRate * STREAMING_TTS_TRANSITION_FADE_SECONDS,
      ),
    },
  });
  node.port.onmessage = (event: MessageEvent<WorkletStatusEvent>) => {
    if (playback.closed || activePlayback !== playback) return;
    if (event.data?.type === 'started' || event.data?.type === 'resumed') {
      setStreamAudioStatus(root, 'Streaming response audio…');
      return;
    }
    if (event.data?.type === 'underrun') {
      setStreamAudioStatus(root, 'Rebuffering streaming response audio…');
      return;
    }
    if (event.data?.type === 'drained' && playback.serverDone) finishPlayback(root, playback);
  };
  node.connect(playback.audioContext.destination);
  return node;
}

function enqueuePcmBytes(playback: MessageStreamPlayback, buffer: ArrayBuffer): void {
  if (playback.closed || !playback.node || buffer.byteLength < 2) return;
  const evenByteLength = buffer.byteLength - (buffer.byteLength % 2);
  const samples = new Int16Array(buffer.slice(0, evenByteLength));
  const floatSamples = pcm16ToFloat32(samples, playback.sampleRate, playback.audioContext.sampleRate);
  playback.node.port.postMessage(
    { type: 'push', samples: floatSamples },
    [floatSamples.buffer],
  );
}

function markServerDone(playback: MessageStreamPlayback): void {
  if (playback.closed || playback.serverDone) return;
  playback.serverDone = true;
  playback.node?.port.postMessage({ type: 'end' });
}

function finishPlayback(root: ParentNode, playback: MessageStreamPlayback): void {
  if (playback.closed) return;
  playback.closed = true;
  if (activePlayback === playback) activePlayback = null;
  setButtonStreaming(playback.button, false);
  try { playback.socket?.close(); } catch { /* ignore connection cleanup failures */ }
  try { playback.node?.disconnect(); } catch { /* ignore browser cleanup failures */ }
  void playback.audioContext.close().catch(() => undefined);
  setStreamAudioStatus(root, 'Streaming response audio finished.');
}

function terminatePlayback(playback: MessageStreamPlayback): void {
  if (playback.closed) return;
  playback.closed = true;
  try { playback.socket?.close(); } catch { /* ignore connection cleanup failures */ }
  try { playback.node?.port.postMessage({ type: 'stop' }); } catch { /* ignore browser cleanup failures */ }
  try { playback.node?.disconnect(); } catch { /* ignore browser cleanup failures */ }
  void playback.audioContext.close().catch(() => undefined);
}

function streamingTtsWebSocketUrl(): string {
  const url = new URL(STREAMING_TTS_WEBSOCKET_PATH, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

function createAudioWorkletModuleUrl(): { url: string; revoke: () => void } {
  const source = assistantPcmStreamWorkletSource();
  if (typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
    return { url, revoke: () => URL.revokeObjectURL(url) };
  }
  return {
    url: `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`,
    revoke: () => undefined,
  };
}

function assistantPcmStreamWorkletSource(): string {
  return `
class OmnixAssistantPcmStreamProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const settings = options.processorOptions || {};
    this.startBufferSamples = Math.max(1, Number(settings.startBufferSamples) || sampleRate * 2);
    this.rebufferSamples = Math.max(1, Number(settings.rebufferSamples) || sampleRate * 1.5);
    this.maxRebufferSamples = Math.max(
      this.rebufferSamples,
      Number(settings.maxRebufferSamples) || sampleRate * 3,
    );
    this.currentRebufferSamples = this.rebufferSamples;
    this.transitionFadeSamples = Math.max(
      1,
      Number(settings.transitionFadeSamples) || Math.round(sampleRate * 0.008),
    );
    this.queue = [];
    this.headOffset = 0;
    this.queuedSamples = 0;
    this.started = false;
    this.waitingForBuffer = false;
    this.inputEnded = false;
    this.stopped = false;
    this.drained = false;
    this.fadeInRemaining = 0;
    this.underrunCount = 0;
    this.port.onmessage = (event) => {
      const message = event.data || {};
      if (message.type === 'push' && message.samples) {
        const samples = message.samples instanceof Float32Array
          ? message.samples
          : new Float32Array(message.samples);
        if (samples.length > 0) {
          this.queue.push(samples);
          this.queuedSamples += samples.length;
          this.maybeStartOrResume();
        }
        return;
      }
      if (message.type === 'end') {
        this.inputEnded = true;
        this.maybeStartOrResume();
        return;
      }
      if (message.type === 'stop') this.stopped = true;
    };
  }

  beginFadeIn() {
    this.fadeInRemaining = this.transitionFadeSamples;
  }

  maybeStartOrResume() {
    if (!this.started && (this.queuedSamples >= this.startBufferSamples || (this.inputEnded && this.queuedSamples > 0))) {
      this.started = true;
      this.waitingForBuffer = false;
      this.beginFadeIn();
      this.port.postMessage({ type: 'started', buffered_samples: this.queuedSamples });
      return;
    }
    if (
      this.started
      && this.waitingForBuffer
      && (this.queuedSamples >= this.currentRebufferSamples || this.inputEnded)
    ) {
      this.waitingForBuffer = false;
      this.beginFadeIn();
      this.port.postMessage({ type: 'resumed', buffered_samples: this.queuedSamples });
    }
  }

  applyFadeIn(channel, written) {
    let index = 0;
    while (index < written && this.fadeInRemaining > 0) {
      const elapsed = this.transitionFadeSamples - this.fadeInRemaining + 1;
      const progress = Math.min(1, elapsed / this.transitionFadeSamples);
      const gain = 0.5 * (1 - Math.cos(Math.PI * progress));
      channel[index] *= gain;
      this.fadeInRemaining -= 1;
      index += 1;
    }
  }

  applyFadeOut(channel, written) {
    const fadeSamples = Math.min(written, this.transitionFadeSamples);
    const start = written - fadeSamples;
    for (let index = 0; index < fadeSamples; index += 1) {
      const progress = (index + 1) / fadeSamples;
      const gain = 0.5 * (1 + Math.cos(Math.PI * progress));
      channel[start + index] *= gain;
    }
  }

  beginRebuffering() {
    this.waitingForBuffer = true;
    this.underrunCount += 1;
    const multiplier = 1 + (Math.max(0, this.underrunCount - 1) * 0.5);
    this.currentRebufferSamples = Math.min(
      this.maxRebufferSamples,
      Math.round(this.rebufferSamples * multiplier),
    );
    this.port.postMessage({
      type: 'underrun',
      buffered_samples: this.queuedSamples,
      target_samples: this.currentRebufferSamples,
    });
  }

  signalDrained() {
    if (!this.drained) {
      this.drained = true;
      this.port.postMessage({ type: 'drained' });
    }
    return false;
  }

  process(_inputs, outputs) {
    const channel = outputs[0] && outputs[0][0];
    if (!channel) return !this.stopped;
    channel.fill(0);
    if (this.stopped) return false;

    this.maybeStartOrResume();
    if (!this.started || this.waitingForBuffer) {
      if (this.inputEnded && this.queuedSamples === 0) return this.signalDrained();
      return true;
    }

    let written = 0;
    while (written < channel.length && this.queue.length > 0) {
      const head = this.queue[0];
      const available = head.length - this.headOffset;
      const take = Math.min(available, channel.length - written);
      channel.set(head.subarray(this.headOffset, this.headOffset + take), written);
      written += take;
      this.headOffset += take;
      this.queuedSamples -= take;
      if (this.headOffset >= head.length) {
        this.queue.shift();
        this.headOffset = 0;
      }
    }

    this.applyFadeIn(channel, written);
    if (this.queuedSamples === 0) {
      this.applyFadeOut(channel, written);
      if (this.inputEnded) return this.signalDrained();
      this.beginRebuffering();
    }
    return true;
  }
}
registerProcessor('${STREAMING_TTS_WORKLET_NAME}', OmnixAssistantPcmStreamProcessor);
`;
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

function parseStreamingTtsControlEvent(value: string): StreamingTtsControlEvent | null {
  try { return JSON.parse(value) as StreamingTtsControlEvent; } catch { return null; }
}

function pcm16ToFloat32(input: Int16Array, sourceSampleRate: number, targetSampleRate: number): Float32Array {
  if (sourceSampleRate === targetSampleRate) {
    const output = new Float32Array(input.length);
    for (let index = 0; index < input.length; index += 1) output[index] = input[index] / 32768;
    return output;
  }

  const outputLength = Math.max(1, Math.round(input.length * targetSampleRate / sourceSampleRate));
  const output = new Float32Array(outputLength);
  const sourceStep = sourceSampleRate / targetSampleRate;
  for (let index = 0; index < outputLength; index += 1) {
    const sourcePosition = Math.min(input.length - 1, index * sourceStep);
    const leftIndex = Math.floor(sourcePosition);
    const rightIndex = Math.min(input.length - 1, leftIndex + 1);
    const fraction = sourcePosition - leftIndex;
    const left = input[leftIndex] / 32768;
    const right = input[rightIndex] / 32768;
    output[index] = left + ((right - left) * fraction);
  }
  return output;
}
