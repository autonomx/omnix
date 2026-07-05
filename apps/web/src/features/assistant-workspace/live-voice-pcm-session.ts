import type { LiveCallDiagnosticsReporter } from './live-call-diagnostics-client';
import { LIVE_VOICE_PCM_WORKLET_NAME, liveVoicePcmWorkletSource } from './live-voice-pcm-worklet';

const SAMPLE_RATE = 24_000;
const START_BUFFER_SECONDS = 2.0;
const REBUFFER_SECONDS = 1.5;
const MAX_REBUFFER_SECONDS = 3.0;
const TRANSITION_FADE_SECONDS = 0.008;
const TTS_WEBSOCKET_PATH = '/api/tts/stream/websocket';
const TTS_CHUNK_SIZE = 8;
const DRAIN_TIMEOUT_MS = 120_000;

type StreamingAudioWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
  AudioWorkletNode?: typeof AudioWorkletNode;
  WebSocket?: typeof WebSocket;
};

type ControlEvent = {
  type?: string;
  message?: string;
  sample_rate?: number;
  stream_id?: string;
  partial?: boolean;
};

type WorkletEvent = {
  type?: string;
  buffered_samples?: number;
  incoming_samples?: number;
  target_samples?: number;
  render_clock_samples?: number;
  played_samples?: number;
  underrun_count?: number;
  current_rebuffer_samples?: number;
  waiting_for_buffer?: boolean;
  input_ended?: boolean;
};

type PhraseStats = {
  frameCount: number;
  receivedBytes: number;
  receivedSamples: number;
  firstFrameAtMs: number | null;
  lastFrameAtMs: number | null;
  sampleRate: number;
};

export type LiveVoicePcmSession = {
  enqueuePhrase: (text: string, phraseIndex: number) => Promise<void>;
  finish: () => Promise<void>;
  stop: (reason?: string) => Promise<void>;
  isClosed: () => boolean;
};

export async function createLiveVoicePcmSession(
  traceId: string,
  voiceId: string | null,
  reporter: LiveCallDiagnosticsReporter,
): Promise<LiveVoicePcmSession> {
  const liveWindow = window as StreamingAudioWindow;
  const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
  const AudioWorkletNodeCtor = liveWindow.AudioWorkletNode;
  const WebSocketCtor = liveWindow.WebSocket;
  if (!AudioContextCtor || !AudioWorkletNodeCtor || !WebSocketCtor) {
    throw new Error('Live voice streaming requires AudioWorklet and WebSocket support.');
  }

  const startedAtMs = performance.now();
  const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: SAMPLE_RATE });
  if (audioContext.state !== 'running') await audioContext.resume();
  const moduleUrl = createWorkletModuleUrl();
  try {
    await audioContext.audioWorklet.addModule(moduleUrl.url);
  } finally {
    moduleUrl.revoke();
  }

  let closed = false;
  let inputFinished = false;
  let generationQueue: Promise<void> = Promise.resolve();
  let activeSocket: WebSocket | null = null;
  let drained = false;
  let drainResolve: (() => void) | null = null;
  let drainReject: ((error: Error) => void) | null = null;
  let totalFrames = 0;
  let totalReceivedSamples = 0;
  let underruns = 0;
  let resumes = 0;
  const drainPromise = new Promise<void>((resolve, reject) => {
    drainResolve = resolve;
    drainReject = reject;
  });

  const node = new AudioWorkletNodeCtor(audioContext, LIVE_VOICE_PCM_WORKLET_NAME, {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: {
      startBufferSamples: Math.round(audioContext.sampleRate * START_BUFFER_SECONDS),
      rebufferSamples: Math.round(audioContext.sampleRate * REBUFFER_SECONDS),
      maxRebufferSamples: Math.round(audioContext.sampleRate * MAX_REBUFFER_SECONDS),
      transitionFadeSamples: Math.round(audioContext.sampleRate * TRANSITION_FADE_SECONDS),
    },
  });

  node.port.onmessage = (event: MessageEvent<WorkletEvent>) => {
    if (closed) return;
    const eventType = event.data?.type ?? 'unknown';
    if (eventType === 'underrun') underruns += 1;
    if (eventType === 'resumed') resumes += 1;
    reporter.record(`worklet_${eventType}`, {
      ...event.data,
      audio_context_state: audioContext.state,
      total_frames: totalFrames,
      total_received_samples: totalReceivedSamples,
      total_received_audio_ms: totalReceivedSamples * 1000 / SAMPLE_RATE,
      underruns,
      resumes,
    }, 'audio_worklet');
    if (eventType === 'drained') {
      drained = true;
      drainResolve?.();
    }
  };
  node.connect(audioContext.destination);

  reporter.record('pcm_session_created', {
    voice_id: voiceId,
    audio_context_sample_rate: audioContext.sampleRate,
    audio_context_state: audioContext.state,
    start_buffer_samples: Math.round(audioContext.sampleRate * START_BUFFER_SECONDS),
    rebuffer_samples: Math.round(audioContext.sampleRate * REBUFFER_SECONDS),
    max_rebuffer_samples: Math.round(audioContext.sampleRate * MAX_REBUFFER_SECONDS),
    transition_fade_samples: Math.round(audioContext.sampleRate * TRANSITION_FADE_SECONDS),
  }, 'pcm_session');

  const streamPhrase = (text: string, phraseIndex: number): Promise<void> => new Promise((resolve, reject) => {
    if (closed) {
      reject(new Error('Live voice PCM session is closed.'));
      return;
    }
    const phraseStartedAtMs = performance.now();
    const stats: PhraseStats = {
      frameCount: 0,
      receivedBytes: 0,
      receivedSamples: 0,
      firstFrameAtMs: null,
      lastFrameAtMs: null,
      sampleRate: SAMPLE_RATE,
    };
    const phraseStreamId = createPhraseStreamId(traceId, phraseIndex);
    const socket = new WebSocketCtor(ttsWebSocketUrl());
    activeSocket = socket;
    socket.binaryType = 'arraybuffer';
    let completed = false;

    const fail = (error: Error) => {
      if (completed) return;
      completed = true;
      reporter.record('phrase_generation_failed', {
        phrase_index: phraseIndex,
        phrase_stream_id: phraseStreamId,
        text,
        text_length: text.length,
        elapsed_ms: performance.now() - phraseStartedAtMs,
        error: error.message,
      }, 'pcm_session');
      reject(error);
    };

    socket.addEventListener('open', () => {
      if (closed) {
        socket.close(1000, 'session-closed');
        return;
      }
      reporter.record('phrase_websocket_opened', {
        phrase_index: phraseIndex,
        phrase_stream_id: phraseStreamId,
        text_length: text.length,
        queue_delay_ms: phraseStartedAtMs - startedAtMs,
      }, 'pcm_session');
      socket.send(JSON.stringify({
        text,
        speaker: voiceId,
        language: 'English',
        chunk_size: TTS_CHUNK_SIZE,
        temperature: 0.6,
        top_k: 20,
        top_p: 0.85,
        repetition_penalty: 1.0,
        append_silence: false,
        non_streaming_mode: false,
        parity_mode: false,
        diagnostics_stream_id: phraseStreamId,
      }));
    }, { once: true });

    socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (closed || completed) return;
      if (event.data instanceof ArrayBuffer) {
        const now = performance.now();
        if (stats.firstFrameAtMs === null) {
          stats.firstFrameAtMs = now;
          reporter.record('phrase_first_frame_received', {
            phrase_index: phraseIndex,
            phrase_stream_id: phraseStreamId,
            first_frame_delay_ms: now - phraseStartedAtMs,
          }, 'pcm_session');
        }
        stats.lastFrameAtMs = now;
        stats.frameCount += 1;
        stats.receivedBytes += event.data.byteLength;
        const sourceSamples = Math.floor(event.data.byteLength / 2);
        stats.receivedSamples += sourceSamples;
        totalFrames += 1;
        totalReceivedSamples += sourceSamples;
        const converted = pcm16ToFloat32(
          new Int16Array(event.data.slice(0, event.data.byteLength - (event.data.byteLength % 2))),
          stats.sampleRate,
          audioContext.sampleRate,
        );
        node.port.postMessage({ type: 'push', samples: converted }, [converted.buffer]);
        return;
      }

      const message = parseControlEvent(event.data);
      if (!message) return;
      if (message.type === 'start' || message.type === 'format') {
        if (typeof message.sample_rate === 'number' && message.sample_rate > 0) {
          stats.sampleRate = message.sample_rate;
        }
        return;
      }
      if (message.type === 'error') {
        fail(new Error(message.message || 'Live voice phrase generation failed.'));
        return;
      }
      if (message.type === 'done') {
        completed = true;
        const elapsedMs = performance.now() - phraseStartedAtMs;
        const audioMs = stats.receivedSamples * 1000 / Math.max(1, stats.sampleRate);
        reporter.record('phrase_buffered', {
          phrase_index: phraseIndex,
          phrase_stream_id: phraseStreamId,
          text,
          text_length: text.length,
          partial: message.partial ?? false,
          frames: stats.frameCount,
          received_bytes: stats.receivedBytes,
          received_samples: stats.receivedSamples,
          audio_ms: audioMs,
          elapsed_ms: elapsedMs,
          generation_rtf: audioMs > 0 ? elapsedMs / audioMs : null,
          first_frame_delay_ms: stats.firstFrameAtMs === null ? null : stats.firstFrameAtMs - phraseStartedAtMs,
        }, 'pcm_session');
        try {
          socket.send(JSON.stringify({
            type: 'diagnostic',
            stream_id: phraseStreamId,
            event: 'phrase_buffered',
            details: {
              phrase_index: phraseIndex,
              frames: stats.frameCount,
              received_samples: stats.receivedSamples,
              audio_ms: audioMs,
              elapsed_ms: elapsedMs,
            },
          }));
        } catch {
          // The separate live-call log still records completion.
        }
        resolve();
      }
    });

    socket.addEventListener('error', () => fail(new Error('Live voice phrase WebSocket failed.')));
    socket.addEventListener('close', (event: CloseEvent) => {
      if (activeSocket === socket) activeSocket = null;
      reporter.record('phrase_websocket_closed', {
        phrase_index: phraseIndex,
        phrase_stream_id: phraseStreamId,
        close_code: event.code,
        close_reason: event.reason,
        clean: event.wasClean,
        completed,
      }, 'pcm_session');
      if (!closed && !completed) fail(new Error('Live voice phrase WebSocket closed before completion.'));
    });
  });

  const enqueuePhrase = (text: string, phraseIndex: number): Promise<void> => {
    if (closed || inputFinished) return Promise.reject(new Error('Live voice input is already closed.'));
    reporter.record('phrase_generation_queued', {
      phrase_index: phraseIndex,
      text,
      text_length: text.length,
    }, 'pcm_session');
    const task = generationQueue.catch(() => undefined).then(() => {
      reporter.record('phrase_generation_started', {
        phrase_index: phraseIndex,
        text_length: text.length,
      }, 'pcm_session');
      return streamPhrase(text, phraseIndex);
    });
    generationQueue = task;
    return task;
  };

  const cleanup = async (reason: string): Promise<void> => {
    if (closed) return;
    closed = true;
    reporter.record('pcm_session_cleanup', {
      reason,
      elapsed_ms: performance.now() - startedAtMs,
      drained,
      total_frames: totalFrames,
      total_received_samples: totalReceivedSamples,
      total_received_audio_ms: totalReceivedSamples * 1000 / SAMPLE_RATE,
      underruns,
      resumes,
    }, 'pcm_session');
    try { activeSocket?.close(1000, reason.slice(0, 120)); } catch { /* ignore cleanup failures */ }
    try { node.port.postMessage({ type: 'stop' }); } catch { /* ignore cleanup failures */ }
    try { node.disconnect(); } catch { /* ignore cleanup failures */ }
    await audioContext.close().catch(() => undefined);
    if (!drained) drainReject?.(new Error(`Live voice PCM session closed: ${reason}`));
  };

  const finish = async (): Promise<void> => {
    if (closed || inputFinished) return;
    inputFinished = true;
    reporter.record('turn_input_finished', {}, 'pcm_session');
    await generationQueue;
    if (closed) return;
    node.port.postMessage({ type: 'end' });
    await withTimeout(drainPromise, DRAIN_TIMEOUT_MS, 'Live voice playback drain timed out.');
    reporter.record('turn_playback_drained', {
      elapsed_ms: performance.now() - startedAtMs,
      total_frames: totalFrames,
      total_received_samples: totalReceivedSamples,
      total_received_audio_ms: totalReceivedSamples * 1000 / SAMPLE_RATE,
      underruns,
      resumes,
    }, 'pcm_session');
    await cleanup('finished');
  };

  const stop = async (reason = 'stopped'): Promise<void> => {
    inputFinished = true;
    await cleanup(reason);
  };

  return { enqueuePhrase, finish, stop, isClosed: () => closed };
}

function createPhraseStreamId(traceId: string, phraseIndex: number): string {
  const safeTrace = traceId.replace(/[^A-Za-z0-9_.-]+/g, '-').slice(-48);
  return `chat-live-${safeTrace}-p${phraseIndex}`.slice(0, 80);
}

function ttsWebSocketUrl(): string {
  const url = new URL(TTS_WEBSOCKET_PATH, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

function createWorkletModuleUrl(): { url: string; revoke: () => void } {
  const source = liveVoicePcmWorkletSource();
  if (typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
    return { url, revoke: () => URL.revokeObjectURL(url) };
  }
  return {
    url: `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`,
    revoke: () => undefined,
  };
}

function parseControlEvent(value: string): ControlEvent | null {
  try { return JSON.parse(value) as ControlEvent; } catch { return null; }
}

function pcm16ToFloat32(input: Int16Array, sourceRate: number, targetRate: number): Float32Array {
  if (sourceRate === targetRate) {
    const output = new Float32Array(input.length);
    for (let index = 0; index < input.length; index += 1) output[index] = input[index] / 32768;
    return output;
  }
  const outputLength = Math.max(1, Math.round(input.length * targetRate / sourceRate));
  const output = new Float32Array(outputLength);
  const sourceStep = sourceRate / targetRate;
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

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}
