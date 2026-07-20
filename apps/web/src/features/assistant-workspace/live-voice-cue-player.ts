import { cloneCueSamples, type LiveVoiceCueId } from './live-voice-cue-bank';

let context: AudioContext | null = null;
let activeSource: AudioBufferSourceNode | null = null;

export async function playLowLatencyVoiceCue(
  cueId: LiveVoiceCueId,
  variantId: string,
  gainValue = 0.75,
): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  const AudioContextCtor = window.AudioContext
    ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) return false;
  if (!context || context.state === 'closed') {
    context = new AudioContextCtor({ latencyHint: 'interactive' });
  }
  if (context.state !== 'running') await context.resume().catch(() => undefined);
  if (context.state !== 'running') return false;

  stopLowLatencyVoiceCue();
  const samples = cloneCueSamples(cueId, variantId, context.sampleRate);
  const buffer = context.createBuffer(1, samples.length, context.sampleRate);
  buffer.copyToChannel(samples, 0);
  const source = context.createBufferSource();
  const gain = context.createGain();
  gain.gain.value = Math.max(0, Math.min(1, gainValue));
  source.buffer = buffer;
  source.connect(gain);
  gain.connect(context.destination);
  activeSource = source;
  return new Promise<boolean>((resolve) => {
    source.addEventListener('ended', () => {
      if (activeSource === source) activeSource = null;
      resolve(true);
    }, { once: true });
    source.start();
  });
}

export function stopLowLatencyVoiceCue(): void {
  const source = activeSource;
  activeSource = null;
  if (!source) return;
  try { source.stop(); } catch { /* already stopped */ }
  try { source.disconnect(); } catch { /* already disconnected */ }
}

export async function closeLowLatencyVoiceCuePlayer(): Promise<void> {
  stopLowLatencyVoiceCue();
  const current = context;
  context = null;
  await current?.close().catch(() => undefined);
}
