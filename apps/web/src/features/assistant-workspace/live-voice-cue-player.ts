import { cloneCueSamples, type LiveVoiceCueId } from './live-voice-cue-bank';
import { createCueSegmentId } from './live-voice-playback-contract';

const CUE_SEGMENT_EVENT = 'omnix:live-voice-cue-segment';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';

type ActiveCue = {
  source: AudioBufferSourceNode;
  segmentId: string;
  cueId: LiveVoiceCueId;
  variantId: string;
  terminal: boolean;
};

let context: AudioContext | null = null;
let activeCue: ActiveCue | null = null;
let cueSequence = 0;
let listenersInstalled = false;

export async function playLowLatencyVoiceCue(
  cueId: LiveVoiceCueId,
  variantId: string,
  gainValue = 0.75,
): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  installCueCancellationListeners();
  const AudioContextCtor = window.AudioContext
    ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) return false;
  if (!context || context.state === 'closed') {
    context = new AudioContextCtor({ latencyHint: 'interactive' });
  }
  if (context.state !== 'running') await context.resume().catch(() => undefined);
  if (context.state !== 'running') return false;

  stopLowLatencyVoiceCue('superseded');
  const samples = cloneCueSamples(cueId, variantId, context.sampleRate);
  const buffer = context.createBuffer(1, samples.length, context.sampleRate);
  buffer.copyToChannel(new Float32Array(samples), 0);
  const source = context.createBufferSource();
  const gain = context.createGain();
  gain.gain.value = Math.max(0, Math.min(1, gainValue));
  source.buffer = buffer;
  source.connect(gain);
  gain.connect(context.destination);
  const segmentId = createCueSegmentId('standalone', cueId, cueSequence++);
  const active: ActiveCue = { source, segmentId, cueId, variantId, terminal: false };
  activeCue = active;
  dispatchCueLifecycle('segment_started', active);
  return new Promise<boolean>((resolve) => {
    source.addEventListener('ended', () => {
      if (!active.terminal) {
        active.terminal = true;
        dispatchCueLifecycle('segment_completed', active);
      }
      if (activeCue === active) activeCue = null;
      resolve(true);
    }, { once: true });
    source.start();
  });
}

export function stopLowLatencyVoiceCue(reason = 'stopped'): void {
  const active = activeCue;
  activeCue = null;
  if (!active) return;
  if (!active.terminal) {
    active.terminal = true;
    dispatchCueLifecycle('segment_interrupted', active, reason);
  }
  try { active.source.stop(); } catch { /* already stopped */ }
  try { active.source.disconnect(); } catch { /* already disconnected */ }
}

export async function closeLowLatencyVoiceCuePlayer(): Promise<void> {
  stopLowLatencyVoiceCue('player_closed');
  const current = context;
  context = null;
  await current?.close().catch(() => undefined);
}

function installCueCancellationListeners(): void {
  if (listenersInstalled || typeof window === 'undefined') return;
  listenersInstalled = true;
  window.addEventListener(INTERRUPT_EVENT, () => stopLowLatencyVoiceCue('voice_interrupt'));
  window.addEventListener(STOP_EVENT, () => stopLowLatencyVoiceCue('live_call_stop'));
}

function dispatchCueLifecycle(
  type: 'segment_started' | 'segment_completed' | 'segment_interrupted',
  active: ActiveCue,
  reason?: string,
): void {
  window.dispatchEvent(new CustomEvent(CUE_SEGMENT_EVENT, {
    detail: {
      type,
      segment_id: active.segmentId,
      segment_kind: 'cue',
      cue_id: active.cueId,
      variant_id: active.variantId,
      semantic_speech_samples: 0,
      reason: reason ?? null,
    },
  }));
}
