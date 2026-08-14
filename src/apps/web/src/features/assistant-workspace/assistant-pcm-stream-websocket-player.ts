import { createAssistantWorkspaceRuntimeConfig } from './runtime-config';

const STREAM_AUDIO_STATUS_ATTRIBUTE = 'data-omnix-stream-audio-status';
const STREAMING_TTS_SAMPLE_RATE = 24_000;
const STREAMING_TTS_START_BUFFER_SECONDS = 0.4;
const STREAMING_TTS_REBUFFER_SECONDS = 0.75;
const STREAMING_TTS_MAX_REBUFFER_SECONDS = 1.5;
const STREAMING_TTS_TRANSITION_FADE_SECONDS = 0.008;
const STREAMING_TTS_WEBSOCKET_PATH = '/api/tts/stream/websocket';
const STREAMING_TTS_CHUNK_SIZE = 8;
const STREAMING_TTS_WORKLET_NAME = 'omnix-assistant-pcm-stream';
const AVATAR_PCM_EVENT = 'omnix:character-avatar-pcm';

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
  stream_id?: string;
  diagnostics_log?: string;
  partial?: boolean;
};

type WorkletStatusEvent = {
  type?: string;
  buffered_samples?: number;
  incoming_samples?: number;
  target_samples?: number;
  rendered_samples?: number;
  render_clock_samples?: number;
  played_samples?: number;
  underrun_count?: number;
  current_rebuffer_samples?: number;
  waiting_for_buffer?: boolean;
  input_ended?: boolean;
};

type StreamStats = {
  websocketOpenedAtMs: number | null;
  firstFrameAtMs: number | null;
  lastFrameAtMs: number | null;
  networkFrames: number;
  receivedBytes: number;
  receivedSamples: number;
  convertedSamples: number;
  workletEvents: number;
  underruns: number;
  resumes: number;
};

type MessageStreamPlayback = {
  button: HTMLButtonElement;
  audioContext: AudioContext;
  node: AudioWorkletNode | null;
  socket: WebSocket | null;
  sampleRate: number;
  serverDone: boolean;
  closed: boolean;
  streamId: string;
  startedAtMs: number;
  stats: StreamStats;
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
    streamId: createStreamId(),
    startedAtMs: performance.now(),
    stats: {
      websocketOpenedAtMs: null,
      firstFrameAtMs: null,
      lastFrameAtMs: null,
      networkFrames: 0,
      receivedBytes: 0,
      receivedSamples: 0,
      convertedSamples: 0,
      workletEvents: 0,
      underruns: 0,
      resumes: 0,
    },
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
    sendDiagnostic(playback, 'playback_failed', {
      error: error instanceof Error ? error.message : String(error),
    });
    terminatePlayback(playback, 'failed');
    if (activePlayback === playback) activePlayback = null;
    setButtonStreaming(button, false);
    setStreamAudioStatus(root, error instanceof Error ? error.message : 'Streaming response audio failed.');
  }
}

export function stopAssistantPcmStream(root: ParentNode, status?: string): void {
  const playback = activePlayback;
  activePlayback = null;
  if (!playback) return;
  sendDiagnostic(playback, 'playback_stopped', { requested_status: status ?? null });
  terminatePlayback(playback, 'stopped');
  setButtonStreaming(playback.button, false);
  if (status) setStreamAudioStatus(root, status);
}

function streamPcmWebSocket(
  playback: MessageStreamPlayback,
  WebSocketCtor: typeof WebSocket,
  text: string,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const socketUrl = streamingTtsWebSocketUrl();
    const socket = new WebSocketCtor(socketUrl);
    playback.socket = socket;
    socket.binaryType = 'arraybuffer';

    socket.addEventListener('open', () => {
      if (playback.closed) {
        socket.close();
        return;
      }
      playback.stats.websocketOpenedAtMs = performance.now();
      const voice = selectedVoiceId();
      socket.send(JSON.stringify({
        text,
        speaker: voice,
        language: 'English',
        chunk_size: STREAMING_TTS_CHUNK_SIZE,
        temperature: 0.6,
        top_k: 20,
        top_p: 0.85,
        repetition_penalty: 1.0,
        append_silence: false,
        non_streaming_mode: false,
        parity_mode: true,
        diagnostics_stream_id: playback.streamId,
      }));
      const audioContextWithLatency = playback.audioContext as AudioContext & { outputLatency?: number };
      const navigatorWithMemory = navigator as Navigator & { deviceMemory?: number };
      sendDiagnostic(playback, 'websocket_opened', {
        websocket_url: socketUrl,
        text_length: text.length,
        text_preview: text.slice(0, 300),
        speaker: voice,
        browser_user_agent: navigator.userAgent,
        hardware_concurrency: navigator.hardwareConcurrency,
        device_memory_gb: navigatorWithMemory.deviceMemory ?? null,
        document_visibility: document.visibilityState,
        audio_context_state: playback.audioContext.state,
        audio_context_sample_rate: playback.audioContext.sampleRate,
        audio_context_base_latency_ms: playback.audioContext.baseLatency * 1000,
        audio_context_output_latency_ms: (audioContextWithLatency.outputLatency ?? 0) * 1000,
      });
    }, { once: true });

    socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (playback.closed) return;
      if (event.data instanceof ArrayBuffer) {
        const now = performance.now();
        const isFirstAudioFrame = playback.stats.receivedSamples === 0;
        const previousFrameAtMs = playback.stats.lastFrameAtMs;
        if (playback.stats.firstFrameAtMs === null) playback.stats.firstFrameAtMs = now;
        playback.stats.lastFrameAtMs = now;
        const frameIndex = playback.stats.networkFrames;
        const sourceSamples = Math.floor(event.data.byteLength / 2);
        playback.stats.networkFrames += 1;
        playback.stats.receivedBytes += event.data.byteLength;
        playback.stats.receivedSamples += sourceSamples;
        sendDiagnostic(playback, 'network_frame_received', {
          frame_index: frameIndex,
          bytes: event.data.byteLength,
          source_samples: sourceSamples,
          source_sample_rate: playback.sampleRate,
          interval_since_previous_frame_ms: previousFrameAtMs === null ? null : now - previousFrameAtMs,
          cumulative_received_audio_ms: playback.stats.receivedSamples * 1000 / playback.sampleRate,
          receive_elapsed_ms: now - playback.startedAtMs,
          receive_rtf: playback.stats.receivedSamples > 0
            ? ((now - playback.startedAtMs) / (playback.stats.receivedSamples * 1000 / playback.sampleRate))
            : null,
        });
        const convertedSamples = enqueuePcmBytes(
          playback,
          event.data,
          isFirstAudioFrame ? STREAMING_TTS_START_BUFFER_SECONDS * 1000 : 0,
        );
        playback.stats.convertedSamples += convertedSamples;
        sendDiagnostic(playback, 'network_frame_enqueued', {
          frame_index: frameIndex,
          converted_samples: convertedSamples,
          cumulative_converted_samples: playback.stats.convertedSamples,
        });
        return;
      }
      if (typeof event.data !== 'string') return;
      const message = parseStreamingTtsControlEvent(event.data);
      if (!message) {
        sendDiagnostic(playback, 'control_message_invalid', { raw_length: event.data.length });
        return;
      }
      sendDiagnostic(playback, 'control_message_received', {
        control_type: message.type ?? null,
        server_stream_id: message.stream_id ?? null,
        server_stream_id_matches: message.stream_id ? message.stream_id === playback.streamId : null,
        sample_rate: message.sample_rate ?? null,
        partial: message.partial ?? null,
        message: message.message ?? null,
        diagnostics_log: message.diagnostics_log ?? null,
      });
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
      sendDiagnostic(playback, 'websocket_error');
      if (!playback.closed && !playback.serverDone) reject(new Error('Streaming TTS connection failed.'));
    });
    socket.addEventListener('close', (event: CloseEvent) => {
      sendDiagnostic(playback, 'websocket_closed', {
        close_code: event.code,
        close_reason: event.reason,
        clean: event.wasClean,
      });
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
  sendDiagnostic(playback, 'worklet_module_loaded');

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
    playback.stats.workletEvents += 1;
    const eventType = event.data?.type ?? 'unknown';
    if (eventType === 'underrun') playback.stats.underruns += 1;
    if (eventType === 'resumed') playback.stats.resumes += 1;
    sendDiagnostic(playback, `worklet_${eventType}`, { ...event.data });
    if (eventType === 'started' || eventType === 'resumed') {
      setStreamAudioStatus(root, 'Streaming response audio…');
      return;
    }
    if (eventType === 'underrun') {
      setStreamAudioStatus(root, 'Rebuffering streaming response audio…');
      return;
    }
    if (eventType === 'drained' && playback.serverDone) finishPlayback(root, playback);
  };
  node.connect(playback.audioContext.destination);
  sendDiagnostic(playback, 'worklet_connected', {
    start_buffer_samples: Math.round(playback.audioContext.sampleRate * STREAMING_TTS_START_BUFFER_SECONDS),
    rebuffer_samples: Math.round(playback.audioContext.sampleRate * STREAMING_TTS_REBUFFER_SECONDS),
    max_rebuffer_samples: Math.round(playback.audioContext.sampleRate * STREAMING_TTS_MAX_REBUFFER_SECONDS),
    transition_fade_samples: Math.round(playback.audioContext.sampleRate * STREAMING_TTS_TRANSITION_FADE_SECONDS),
  });
  return node;
}

function enqueuePcmBytes(playback: MessageStreamPlayback, buffer: ArrayBuffer, startDelayMs = 0): number {
  if (playback.closed || !playback.node || buffer.byteLength < 2) return 0;
  const evenByteLength = buffer.byteLength - (buffer.byteLength % 2);
  const samples = new Int16Array(buffer.slice(0, evenByteLength));
  const floatSamples = pcm16ToFloat32(samples, playback.sampleRate, playback.audioContext.sampleRate);
  const convertedSamples = floatSamples.length;
  window.dispatchEvent(new CustomEvent(AVATAR_PCM_EVENT, {
    detail: {
      samples: samples.slice(),
      sampleRate: playback.sampleRate,
      startDelayMs,
    },
  }));
  playback.node.port.postMessage(
    { type: 'push', samples: floatSamples },
    [floatSamples.buffer],
  );
  return convertedSamples;
}

function markServerDone(playback: MessageStreamPlayback): void {
  if (playback.closed || playback.serverDone) return;
  playback.serverDone = true;
  sendDiagnostic(playback, 'server_done_marked');
  playback.node?.port.postMessage({ type: 'end' });
}

function finishPlayback(root: ParentNode, playback: MessageStreamPlayback): void {
  if (playback.closed) return;
  sendDiagnostic(playback, 'playback_finished', finalDiagnostics(playback));
  playback.closed = true;
  if (activePlayback === playback) activePlayback = null;
  setButtonStreaming(playback.button, false);
  try { playback.socket?.close(1000, 'playback-finished'); } catch { /* ignore connection cleanup failures */ }
  try { playback.node?.disconnect(); } catch { /* ignore browser cleanup failures */ }
  void playback.audioContext.close().catch(() => undefined);
  setStreamAudioStatus(root, 'Streaming response audio finished.');
}

function terminatePlayback(playback: MessageStreamPlayback, reason: string): void {
  if (playback.closed) return;
  sendDiagnostic(playback, 'playback_cleanup', { reason, ...finalDiagnostics(playback) });
  playback.closed = true;
  try { playback.socket?.close(1000, reason.slice(0, 120)); } catch { /* ignore connection cleanup failures */ }
  try { playback.node?.port.postMessage({ type: 'stop' }); } catch { /* ignore browser cleanup failures */ }
  try { playback.node?.disconnect(); } catch { /* ignore browser cleanup failures */ }
  void playback.audioContext.close().catch(() => undefined);
}

function sendDiagnostic(playback: MessageStreamPlayback, event: string, details: Record<string, unknown> = {}): void {
  const socket = playback.socket;
  if (!socket || socket.readyState !== 1) return;
  try {
    socket.send(JSON.stringify({
      type: 'diagnostic',
      stream_id: playback.streamId,
      event,
      details: {
        client_elapsed_ms: performance.now() - playback.startedAtMs,
        audio_context_state: playback.audioContext.state,
        websocket_buffered_amount: socket.bufferedAmount,
        document_visibility: document.visibilityState,
        network_frames: playback.stats.networkFrames,
        received_samples: playback.stats.receivedSamples,
        converted_samples: playback.stats.convertedSamples,
        underruns: playback.stats.underruns,
        resumes: playback.stats.resumes,
        ...details,
      },
    }));
  } catch {
    // Diagnostics must never interrupt audio playback.
  }
}

function finalDiagnostics(playback: MessageStreamPlayback): Record<string, unknown> {
  return {
    total_elapsed_ms: performance.now() - playback.startedAtMs,
    server_done: playback.serverDone,
    source_sample_rate: playback.sampleRate,
    network_frames: playback.stats.networkFrames,
    received_bytes: playback.stats.receivedBytes,
    received_samples: playback.stats.receivedSamples,
    received_audio_ms: playback.stats.receivedSamples * 1000 / playback.sampleRate,
    converted_samples: playback.stats.convertedSamples,
    worklet_events: playback.stats.workletEvents,
    underruns: playback.stats.underruns,
    resumes: playback.stats.resumes,
    first_frame_delay_ms: playback.stats.firstFrameAtMs === null
      ? null
      : playback.stats.firstFrameAtMs - playback.startedAtMs,
    websocket_open_delay_ms: playback.stats.websocketOpenedAtMs === null
      ? null
      : playback.stats.websocketOpenedAtMs - playback.startedAtMs,
  };
}

function createStreamId(): string {
  const cryptoWithUuid = globalThis.crypto as Crypto & { randomUUID?: () => string };
  const suffix = cryptoWithUuid?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `chat-${suffix}`;
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
    this.startBufferSamples = Math.max(1, Number(settings.startBufferSamples) || sampleRate * 0.4);
    this.rebufferSamples = Math.max(1, Number(settings.rebufferSamples) || sampleRate * 0.75);
    this.maxRebufferSamples = Math.max(
      this.rebufferSamples,
      Number(settings.maxRebufferSamples) || sampleRate * 1.5,
    );
    this.currentRebufferSamples = this.rebufferSamples;
    this.transitionFadeSamples = Math.max(
      1,
      Number(settings.transitionFadeSamples) || Math.round(sampleRate * 0.008),
    );
    this.progressIntervalSamples = Math.max(128, Math.round(sampleRate * 0.5));
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
    this.renderClockSamples = 0;
    this.playedSamples = 0;
    this.lastProgressSamples = 0;
    this.port.onmessage = (event) => {
      const message = event.data || {};
      if (message.type === 'push' && message.samples) {
        const samples = message.samples instanceof Float32Array
          ? message.samples
          : new Float32Array(message.samples);
        if (samples.length > 0) {
          this.queue.push(samples);
          this.queuedSamples += samples.length;
          this.port.postMessage({
            type: 'buffered',
            buffered_samples: this.queuedSamples,
            incoming_samples: samples.length,
            target_samples: this.waitingForBuffer ? this.currentRebufferSamples : this.startBufferSamples,
            waiting_for_buffer: this.waitingForBuffer,
            input_ended: this.inputEnded,
            underrun_count: this.underrunCount,
            render_clock_samples: this.renderClockSamples,
            played_samples: this.playedSamples,
          });
          this.maybeStartOrResume();
        }
        return;
      }
      if (message.type === 'end') {
        this.inputEnded = true;
        this.port.postMessage({
          type: 'input_ended',
          buffered_samples: this.queuedSamples,
          waiting_for_buffer: this.waitingForBuffer,
          underrun_count: this.underrunCount,
          render_clock_samples: this.renderClockSamples,
          played_samples: this.playedSamples,
        });
        this.maybeStartOrResume();
        return;
      }
      if (message.type === 'stop') {
        this.stopped = true;
        this.port.postMessage({
          type: 'stopped',
          buffered_samples: this.queuedSamples,
          render_clock_samples: this.renderClockSamples,
          played_samples: this.playedSamples,
          underrun_count: this.underrunCount,
        });
      }
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
      this.port.postMessage({
        type: 'started',
        buffered_samples: this.queuedSamples,
        render_clock_samples: this.renderClockSamples,
        played_samples: this.playedSamples,
      });
      return;
    }
    if (
      this.started
      && this.waitingForBuffer
      && (this.queuedSamples >= this.currentRebufferSamples || this.inputEnded)
    ) {
      this.waitingForBuffer = false;
      this.beginFadeIn();
      this.port.postMessage({
        type: 'resumed',
        buffered_samples: this.queuedSamples,
        target_samples: this.currentRebufferSamples,
        underrun_count: this.underrunCount,
        render_clock_samples: this.renderClockSamples,
        played_samples: this.playedSamples,
      });
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
      underrun_count: this.underrunCount,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
      input_ended: this.inputEnded,
    });
  }

  signalDrained() {
    if (!this.drained) {
      this.drained = true;
      this.port.postMessage({
        type: 'drained',
        buffered_samples: this.queuedSamples,
        underrun_count: this.underrunCount,
        render_clock_samples: this.renderClockSamples,
        played_samples: this.playedSamples,
      });
    }
    return false;
  }

  maybeReportProgress() {
    if (this.renderClockSamples - this.lastProgressSamples < this.progressIntervalSamples) return;
    this.lastProgressSamples = this.renderClockSamples;
    this.port.postMessage({
      type: 'render_progress',
      buffered_samples: this.queuedSamples,
      target_samples: this.waitingForBuffer ? this.currentRebufferSamples : 0,
      waiting_for_buffer: this.waitingForBuffer,
      input_ended: this.inputEnded,
      underrun_count: this.underrunCount,
      current_rebuffer_samples: this.currentRebufferSamples,
      render_clock_samples: this.renderClockSamples,
      played_samples: this.playedSamples,
    });
  }

  process(_inputs, outputs) {
    const channel = outputs[0] && outputs[0][0];
    if (!channel) return !this.stopped;
    channel.fill(0);
    this.renderClockSamples += channel.length;
    if (this.stopped) return false;

    this.maybeStartOrResume();
    if (!this.started || this.waitingForBuffer) {
      this.maybeReportProgress();
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

    this.playedSamples += written;
    this.applyFadeIn(channel, written);
    if (this.queuedSamples === 0) {
      this.applyFadeOut(channel, written);
      if (this.inputEnded) return this.signalDrained();
      this.beginRebuffering();
    }
    this.maybeReportProgress();
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
