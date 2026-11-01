/**
 * A response's speech as one continuous stream (evolution roadmap EV-13): its sentences' PCM16 pushed as it arrives
 * into the read-aloud player's audio worklet, which starts once a little is buffered and rebuffers when it runs dry.
 */
import { PCM_STREAM_WORKLET_NAME, PCM_STREAM_WORKLET_URL } from '../assistant';

const SAMPLE_RATE = 24_000;  // the speech service's
const START_BUFFER_SECONDS = 0.4;  // as the read-aloud player buffers
const REBUFFER_SECONDS = 0.75;
const MAX_REBUFFER_SECONDS = 1.5;
const FADE_SECONDS = 0.008;
const RESUME_TIMEOUT_MS = 2_000;  // a browser may hold audio back until the page is interacted with

export interface RpgPcmSink {
  /** Samples of the response, in order. */
  push(samples: Int16Array, sampleRate: number): void;
  /** No more samples: resolves once all of them have been heard (or the sink is stopped). */
  end(): Promise<void>;
  stop(): void;
}

type AudioWindow = Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext };

function toFloat(samples: Int16Array, from: number, to: number): Float32Array {
  const floats = Float32Array.from(samples, (value) => value / 32768);
  if (from === to || !floats.length) return floats;
  const out = new Float32Array(Math.max(1, Math.round(floats.length * to / from)));
  for (let index = 0; index < out.length; index += 1) {
    const at = index * from / to;
    const low = Math.floor(at);
    const high = Math.min(floats.length - 1, low + 1);
    out[index] = floats[low] + (floats[high] - floats[low]) * (at - low);
  }
  return out;
}

/** A sink on this page's audio, or null where the browser has no audio worklet or holds its audio back. */
export async function openPcmSink(): Promise<RpgPcmSink | null> {
  const page = window as AudioWindow;
  const Context = page.AudioContext ?? page.webkitAudioContext;
  if (!Context || typeof AudioWorkletNode === 'undefined') return null;
  const context = new Context({ latencyHint: 'interactive', sampleRate: SAMPLE_RATE });
  try {
    if (context.state !== 'running') {
      await Promise.race([context.resume(), new Promise((_, reject) => {
        window.setTimeout(() => reject(new Error('audio_held_back')), RESUME_TIMEOUT_MS);
      })]);
    }
    await context.audioWorklet.addModule(PCM_STREAM_WORKLET_URL);
  } catch {
    void context.close().catch(() => undefined);
    return null;
  }
  const rate = context.sampleRate;
  const node = new AudioWorkletNode(context, PCM_STREAM_WORKLET_NAME, {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: {
      startBufferSamples: Math.round(rate * START_BUFFER_SECONDS),
      rebufferSamples: Math.round(rate * REBUFFER_SECONDS),
      maxRebufferSamples: Math.round(rate * MAX_REBUFFER_SECONDS),
      transitionFadeSamples: Math.round(rate * FADE_SECONDS),
    },
  });
  node.connect(context.destination);
  let closed = false;
  let heard: (() => void) | null = null;
  const close = () => {
    if (closed) return;
    closed = true;
    try { node.disconnect(); } catch { /* the page is going */ }
    void context.close().catch(() => undefined);
    heard?.();
  };
  node.port.onmessage = (event: MessageEvent<{ type?: string }>) => {
    if (event.data?.type === 'drained' && heard) close();
  };
  return {
    push(samples, sampleRate) {
      if (closed || !samples.length) return;
      const floats = toFloat(samples, sampleRate, rate);
      node.port.postMessage({ type: 'push', samples: floats }, [floats.buffer]);
    },
    end() {
      if (closed) return Promise.resolve();
      return new Promise<void>((resolve) => {
        heard = resolve;
        node.port.postMessage({ type: 'end' });
      });
    },
    stop() {
      if (!closed) node.port.postMessage({ type: 'stop' });
      close();
    },
  };
}
