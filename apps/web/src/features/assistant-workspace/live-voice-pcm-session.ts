import type { LiveCallDiagnosticsReporter } from './live-call-diagnostics-client';
import {
  createSilenceSegmentId,
  createSpeechSegmentId,
  millisecondsToPlaybackSamples,
  type PlaybackStartPolicy,
  type SilenceReason,
} from './live-voice-playback-contract';
import { LIVE_VOICE_PCM_WORKLET_NAME, liveVoicePcmWorkletSource } from './live-voice-pcm-worklet';

const SAMPLE_RATE = 24_000;
const START_BUFFER_SECONDS = 0.4;
const REBUFFER_SECONDS = 0.75;
const MAX_REBUFFER_SECONDS = 1.5;
const TRANSITION_FADE_SECONDS = 0.008;
const TTS_LIVE_CALL_WEBSOCKET_PATH = '/api/tts/live-call/websocket';
const TTS_CHUNK_SIZE = 8;
const DRAIN_TIMEOUT_MS = 120_000;
const CHARACTER_AVATAR_PCM_EVENT = 'omnix:character-avatar-pcm';
const WEBSOCKET_OPEN = 1;

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
  phrase_index?: number;
  partial?: boolean;
};

type WorkletEvent = {
  type?: string;
  sample_rate?: number;
  segment_id?: string;
  segment_kind?: 'speech' | 'silence' | 'cue';
  phrase_index?: number;
  segment_played_samples?: number;
  buffered_samples?: number;
  buffered_speech_samples?: number;
  incoming_samples?: number;
  target_samples?: number;
  render_clock_samples?: number;
  segment_timeline_samples?: number;
  semantic_speech_samples?: number;
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
  playbackSamples: number;
  firstFrameAtMs: number | null;
  lastFrameAtMs: number | null;
  sampleRate: number;
};

type ActivePhrase = {
  text: string;
  phraseIndex: number;
  phraseStreamId: string;
  segmentId: string;
  startedAtMs: number;
  stats: PhraseStats;
  completed: boolean;
  resolve: () => void;
  reject: (error: Error) => void;
};

export type LiveVoicePcmSession = {
  enqueuePhrase: (text: string, phraseIndex: number) => Promise<void>;
  enqueueSilence: (durationMs: number, reason: SilenceReason) => Promise<void>;
  setStartPolicy: (policy: Partial<PlaybackStartPolicy>) => void;
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
  let activePhrase: ActivePhrase | null = null;
  let socketFailure: Error | null = null;
  let socketOpened = false;
  let drained = false;
  let drainResolve: (() => void) | null = null;
  let totalFrames = 0;
  let totalReceivedSamples = 0;
  let totalPlaybackSamples = 0;
  let underruns = 0;
  let resumes = 0;
  let silenceSequence = 0;
  const drainPromise = new Promise<void>((resolve) => {
    drainResolve = resolve;
  });

  const resumeAudioContext = async (reason: string): Promise<void> => {
    const before = audioContext.state;
    if (before === 'closed') {
      reporter.record('audio_context_resume_skipped', { reason, audio_context_state: before }, 'pcm_session');
      return;
    }
    if (before !== 'running') {
      await audioContext.resume().catch((error: unknown) => {
        reporter.record('audio_context_resume_failed', {
          reason,
          audio_context_state: before,
          error: error instanceof Error ? error.message : String(error),
        }, 'pcm_session');
      });
    }
    reporter.record('audio_context_resume_checked', {
      reason,
      audio_context_state_before: before,
      audio_context_state_after: audioContext.state,
      document_visibility: document.visibilityState,
    }, 'pcm_session');
  };

  const handlePlaybackResumeSignal = (event: Event): void => {
    if (closed) return;
    void resumeAudioContext(event.type);
  };
  document.addEventListener('visibilitychange', handlePlaybackResumeSignal);
  window.addEventListener('focus', handlePlaybackResumeSignal);
  window.addEventListener('pageshow', handlePlaybackResumeSignal);

  const startBufferSamples = Math.round(audioContext.sampleRate * START_BUFFER_SECONDS);
  const node = new AudioWorkletNodeCtor(audioContext, LIVE_VOICE_PCM_WORKLET_NAME, {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: {
      startBufferSamples,
      minimumBufferedSpeechSamples: startBufferSamples,
      notBeforeRenderSample: 0,
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
      sample_rate: event.data?.sample_rate ?? audioContext.sampleRate,
      audio_context_state: audioContext.state,
      total_frames: totalFrames,
      total_received_samples: totalReceivedSamples,
      total_playback_samples: totalPlaybackSamples,
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
    start_buffer_samples: startBufferSamples,
    rebuffer_samples: Math.round(audioContext.sampleRate * REBUFFER_SECONDS),
    max_rebuffer_samples: Math.round(audioContext.sampleRate * MAX_REBUFFER_SECONDS),
    transition_fade_samples: Math.round(audioContext.sampleRate * TRANSITION_FADE_SECONDS),
    websocket_scope: 'turn',
  }, 'pcm_session');

  let socketReadyResolve: (() => void) | null = null;
  let socketReadyReject: ((error: Error) => void) | null = null;
  const socketReady = new Promise<void>((resolve, reject) => {
    socketReadyResolve = resolve;
    socketReadyReject = reject;
  });
  const socket = new WebSocketCtor(ttsWebSocketUrl());
  socket.binaryType = 'arraybuffer';
  reporter.record('session_websocket_created', {
    websocket_path: TTS_LIVE_CALL_WEBSOCKET_PATH,
  }, 'pcm_session');

  const failActivePhrase = (error: Error): void => {
    const phrase = activePhrase;
    if (!phrase || phrase.completed) return;
    phrase.completed = true;
    activePhrase = null;
    reporter.record('phrase_generation_failed', {
      segment_id: phrase.segmentId,
      phrase_index: phrase.phraseIndex,
      phrase_stream_id: phrase.phraseStreamId,
      text: phrase.text,
      text_length: phrase.text.length,
      elapsed_ms: performance.now() - phrase.startedAtMs,
      error: error.message,
    }, 'pcm_session');
    phrase.reject(error);
  };

  const handleBinaryFrame = (buffer: ArrayBuffer): void => {
    const phrase = activePhrase;
    if (!phrase || phrase.completed) {
      reporter.record('unexpected_audio_frame', { bytes: buffer.byteLength }, 'pcm_session');
      return;
    }
    const now = performance.now();
    if (phrase.stats.firstFrameAtMs === null) {
      phrase.stats.firstFrameAtMs = now;
      reporter.record('phrase_first_frame_received', {
        segment_id: phrase.segmentId,
        phrase_index: phrase.phraseIndex,
        phrase_stream_id: phrase.phraseStreamId,
        first_frame_delay_ms: now - phrase.startedAtMs,
      }, 'pcm_session');
    }
    phrase.stats.lastFrameAtMs = now;
    phrase.stats.frameCount += 1;
    phrase.stats.receivedBytes += buffer.byteLength;
    const sourceSamples = Math.floor(buffer.byteLength / 2);
    phrase.stats.receivedSamples += sourceSamples;
    totalFrames += 1;
    totalReceivedSamples += sourceSamples;
    const evenBytes = buffer.byteLength - (buffer.byteLength % 2);
    window.dispatchEvent(new CustomEvent(CHARACTER_AVATAR_PCM_EVENT, {
      detail: {
        samples: new Int16Array(buffer.slice(0, evenBytes)),
        sampleRate: phrase.stats.sampleRate,
      },
    }));
    const converted = pcm16ToFloat32(
      new Int16Array(buffer.slice(0, evenBytes)),
      phrase.stats.sampleRate,
      audioContext.sampleRate,
    );
    phrase.stats.playbackSamples += converted.length;
    totalPlaybackSamples += converted.length;
    node.port.postMessage({
      type: 'push_segment_samples',
      segmentId: phrase.segmentId,
      segmentKind: 'speech',
      phraseIndex: phrase.phraseIndex,
      samples: converted,
    }, [converted.buffer]);
  };

  const handleControlMessage = (message: ControlEvent): void => {
    const phrase = activePhrase;
    if (!phrase || phrase.completed) {
      reporter.record('unexpected_control_message', { ...message }, 'pcm_session');
      return;
    }
    if (message.stream_id && message.stream_id !== phrase.phraseStreamId) {
      reporter.record('phrase_stream_id_mismatch', {
        segment_id: phrase.segmentId,
        phrase_index: phrase.phraseIndex,
        expected_stream_id: phrase.phraseStreamId,
        received_stream_id: message.stream_id,
        control_type: message.type,
      }, 'pcm_session');
      return;
    }
    if (message.type === 'start' || message.type === 'format') {
      if (typeof message.sample_rate === 'number' && message.sample_rate > 0) {
        phrase.stats.sampleRate = message.sample_rate;
      }
      return;
    }
    if (message.type === 'error') {
      failActivePhrase(new Error(message.message || 'Live voice phrase generation failed.'));
      return;
    }
    if (message.type !== 'done') return;

    phrase.completed = true;
    node.port.postMessage({ type: 'segment_end', segmentId: phrase.segmentId });
    const elapsedMs = performance.now() - phrase.startedAtMs;
    const audioMs = phrase.stats.receivedSamples * 1000 / Math.max(1, phrase.stats.sampleRate);
    reporter.record('phrase_buffered', {
      segment_id: phrase.segmentId,
      segment_kind: 'speech',
      phrase_index: phrase.phraseIndex,
      phrase_stream_id: phrase.phraseStreamId,
      text: phrase.text,
      text_length: phrase.text.length,
      partial: message.partial ?? false,
      frames: phrase.stats.frameCount,
      received_bytes: phrase.stats.receivedBytes,
      received_samples: phrase.stats.receivedSamples,
      playback_samples: phrase.stats.playbackSamples,
      sample_rate: audioContext.sampleRate,
      audio_ms: audioMs,
      elapsed_ms: elapsedMs,
      generation_rtf: audioMs > 0 ? elapsedMs / audioMs : null,
      first_frame_delay_ms: phrase.stats.firstFrameAtMs === null
        ? null
        : phrase.stats.firstFrameAtMs - phrase.startedAtMs,
    }, 'pcm_session');
    try {
      socket.send(JSON.stringify({
        type: 'diagnostic',
        stream_id: phrase.phraseStreamId,
        event: 'playback_finished',
        details: {
          completion_scope: 'phrase_buffered_into_live_turn',
          segment_id: phrase.segmentId,
          phrase_index: phrase.phraseIndex,
          frames: phrase.stats.frameCount,
          received_samples: phrase.stats.receivedSamples,
          playback_samples: phrase.stats.playbackSamples,
          sample_rate: audioContext.sampleRate,
          audio_ms: audioMs,
          elapsed_ms: elapsedMs,
        },
      }));
    } catch {
      // The separate live-call log still records completion.
    }
    activePhrase = null;
    phrase.resolve();
  };

  socket.addEventListener('open', () => {
    if (closed) {
      socket.close(1000, 'session-closed');
      return;
    }
    socketOpened = true;
    reporter.record('session_websocket_opened', {
      websocket_path: TTS_LIVE_CALL_WEBSOCKET_PATH,
      turn_elapsed_ms: performance.now() - startedAtMs,
    }, 'pcm_session');
    socketReadyResolve?.();
  }, { once: true });

  socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
    if (closed) return;
    if (event.data instanceof ArrayBuffer) {
      handleBinaryFrame(event.data);
      return;
    }
    const message = parseControlEvent(event.data);
    if (message) handleControlMessage(message);
  });

  socket.addEventListener('error', () => {
    const error = new Error('Live voice session WebSocket failed.');
    socketFailure = error;
    if (!socketOpened) socketReadyReject?.(error);
    failActivePhrase(error);
  });

  socket.addEventListener('close', (event: CloseEvent) => {
    reporter.record('session_websocket_closed', {
      close_code: event.code,
      close_reason: event.reason,
      clean: event.wasClean,
      opened: socketOpened,
      session_closed: closed,
    }, 'pcm_session');
    if (closed) return;
    const error = new Error('Live voice session WebSocket closed before turn completion.');
    socketFailure = error;
    if (!socketOpened) socketReadyReject?.(error);
    failActivePhrase(error);
  });

  const streamPhrase = async (text: string, phraseIndex: number): Promise<void> => {
    if (closed) throw new Error('Live voice PCM session is closed.');
    await socketReady;
    if (closed) throw new Error('Live voice PCM session is closed.');
    if (socketFailure) throw socketFailure;
    if (socket.readyState !== WEBSOCKET_OPEN) throw new Error('Live voice session WebSocket is not open.');
    if (activePhrase) throw new Error('Live voice phrase generation is already active.');

    const phraseStartedAtMs = performance.now();
    const phraseStreamId = createPhraseStreamId(traceId, phraseIndex);
    const segmentId = createSpeechSegmentId(traceId, phraseIndex);
    return new Promise<void>((resolve, reject) => {
      activePhrase = {
        text,
        phraseIndex,
        phraseStreamId,
        segmentId,
        startedAtMs: phraseStartedAtMs,
        completed: false,
        resolve,
        reject,
        stats: {
          frameCount: 0,
          receivedBytes: 0,
          receivedSamples: 0,
          playbackSamples: 0,
          firstFrameAtMs: null,
          lastFrameAtMs: null,
          sampleRate: SAMPLE_RATE,
        },
      };
      reporter.record('phrase_request_sent', {
        segment_id: segmentId,
        phrase_index: phraseIndex,
        phrase_stream_id: phraseStreamId,
        text_length: text.length,
        turn_elapsed_ms: phraseStartedAtMs - startedAtMs,
        websocket_reused: true,
      }, 'pcm_session');
      try {
        socket.send(JSON.stringify({
          type: 'synthesize',
          request_id: phraseStreamId,
          phrase_index: phraseIndex,
          segment_id: segmentId,
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
          parity_mode: true,
          diagnostics_stream_id: phraseStreamId,
        }));
      } catch (error) {
        failActivePhrase(error instanceof Error ? error : new Error(String(error)));
      }
    });
  };

  const enqueuePhrase = (text: string, phraseIndex: number): Promise<void> => {
    if (closed || inputFinished) return Promise.reject(new Error('Live voice input is already closed.'));
    reporter.record('phrase_generation_queued', {
      phrase_index: phraseIndex,
      text,
      text_length: text.length,
    }, 'pcm_session');
    const task = generationQueue.catch(() => undefined).then(() => {
      void resumeAudioContext('phrase_generation_started');
      reporter.record('phrase_generation_started', {
        phrase_index: phraseIndex,
        text_length: text.length,
      }, 'pcm_session');
      return streamPhrase(text, phraseIndex);
    });
    generationQueue = task;
    return task;
  };

  const enqueueSilence = (durationMs: number, reason: SilenceReason): Promise<void> => {
    if (closed || inputFinished) return Promise.reject(new Error('Live voice input is already closed.'));
    const durationSamples = millisecondsToPlaybackSamples(durationMs, audioContext.sampleRate);
    if (durationSamples <= 0) return Promise.resolve();
    const segmentId = createSilenceSegmentId(traceId, silenceSequence);
    silenceSequence += 1;
    const task = generationQueue.catch(() => undefined).then(() => {
      node.port.postMessage({
        type: 'push_segment_silence',
        segmentId,
        durationSamples,
        reason,
      });
      reporter.record('silence_segment_queued', {
        segment_id: segmentId,
        segment_kind: 'silence',
        duration_samples: durationSamples,
        duration_ms: durationSamples * 1000 / audioContext.sampleRate,
        sample_rate: audioContext.sampleRate,
        reason,
      }, 'pcm_session');
    });
    generationQueue = task;
    return task;
  };

  const setStartPolicy = (policy: Partial<PlaybackStartPolicy>): void => {
    const notBeforeRenderSample = Math.max(0, Math.round(policy.notBeforeRenderSample ?? 0));
    const minimumBufferedSpeechSamples = Math.max(
      1,
      Math.round(policy.minimumBufferedSpeechSamples ?? startBufferSamples),
    );
    node.port.postMessage({
      type: 'set_start_policy',
      notBeforeRenderSample,
      minimumBufferedSpeechSamples,
    });
    reporter.record('playback_start_policy_set', {
      not_before_render_sample: notBeforeRenderSample,
      minimum_buffered_speech_samples: minimumBufferedSpeechSamples,
      sample_rate: audioContext.sampleRate,
    }, 'pcm_session');
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
      total_playback_samples: totalPlaybackSamples,
      total_received_audio_ms: totalReceivedSamples * 1000 / SAMPLE_RATE,
      underruns,
      resumes,
      websocket_scope: 'turn',
    }, 'pcm_session');
    failActivePhrase(new Error(`Live voice PCM session stopped: ${reason}`));
    if (socket.readyState === WEBSOCKET_OPEN) {
      try { socket.send(JSON.stringify({ type: 'close', reason })); } catch { /* ignore cleanup failures */ }
    }
    try { socket.close(1000, reason.slice(0, 120)); } catch { /* ignore cleanup failures */ }
    try { node.port.postMessage({ type: 'stop' }); } catch { /* ignore cleanup failures */ }
    try { node.disconnect(); } catch { /* ignore cleanup failures */ }
    document.removeEventListener('visibilitychange', handlePlaybackResumeSignal);
    window.removeEventListener('focus', handlePlaybackResumeSignal);
    window.removeEventListener('pageshow', handlePlaybackResumeSignal);
    await audioContext.close().catch(() => undefined);
    if (!drained) drainResolve?.();
  };

  const finish = async (): Promise<void> => {
    if (closed || inputFinished) return;
    inputFinished = true;
    reporter.record('turn_input_finished', {}, 'pcm_session');
    await generationQueue;
    if (closed) return;
    await resumeAudioContext('turn_input_finished');
    node.port.postMessage({ type: 'end' });
    await withTimeout(drainPromise, DRAIN_TIMEOUT_MS, 'Live voice playback drain timed out.');
    reporter.record('turn_playback_drained', {
      elapsed_ms: performance.now() - startedAtMs,
      total_frames: totalFrames,
      total_received_samples: totalReceivedSamples,
      total_playback_samples: totalPlaybackSamples,
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

  return {
    enqueuePhrase,
    enqueueSilence,
    setStartPolicy,
    finish,
    stop,
    isClosed: () => closed,
  };
}

function createPhraseStreamId(traceId: string, phraseIndex: number): string {
  const safeTrace = traceId.replace(/[^A-Za-z0-9_.-]+/g, '-').slice(-48);
  return `chat-live-${safeTrace}-p${phraseIndex}`.slice(0, 80);
}

function ttsWebSocketUrl(): string {
  const url = new URL(TTS_LIVE_CALL_WEBSOCKET_PATH, window.location.href);
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
