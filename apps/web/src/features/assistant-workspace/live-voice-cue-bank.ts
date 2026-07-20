export type LiveVoiceCueId = 'mhm' | 'hmm' | 'inhale' | 'amused_exhale';

const VARIANT_COUNT = 4;
const cache = new Map<string, Float32Array>();

export function cueVariantId(cueId: LiveVoiceCueId, sequence: number): string {
  const bounded = Math.abs(Math.trunc(sequence)) % VARIANT_COUNT;
  return `${cueId}-v${bounded + 1}`;
}

export function cueVariantCount(): number {
  return VARIANT_COUNT;
}

export function getCachedCueSamples(
  cueId: LiveVoiceCueId,
  variantId: string,
  sampleRate: number,
): Float32Array {
  const rate = Math.max(8_000, Math.round(sampleRate));
  const variant = parseVariant(variantId);
  const key = `${cueId}:${variant}:${rate}`;
  const existing = cache.get(key);
  if (existing) return existing;
  const samples = cueId === 'mhm' || cueId === 'hmm'
    ? createHum(cueId, variant, rate)
    : createBreath(cueId, variant, rate);
  cache.set(key, samples);
  return samples;
}

export function cloneCueSamples(
  cueId: LiveVoiceCueId,
  variantId: string,
  sampleRate: number,
): Float32Array {
  return getCachedCueSamples(cueId, variantId, sampleRate).slice();
}

export function clearCueSampleCache(): void {
  cache.clear();
}

function createHum(cueId: 'mhm' | 'hmm', variant: number, sampleRate: number): Float32Array {
  const durationMs = cueId === 'mhm' ? 300 + variant * 22 : 390 + variant * 28;
  const length = Math.max(1, Math.round(sampleRate * durationMs / 1_000));
  const output = new Float32Array(length);
  const base = (cueId === 'mhm' ? 142 : 128) + variant * 3;
  const split = cueId === 'mhm' ? 0.48 : 1;
  for (let index = 0; index < length; index += 1) {
    const progress = index / Math.max(1, length - 1);
    const attack = Math.min(1, progress / 0.12);
    const release = Math.min(1, (1 - progress) / 0.2);
    const envelope = smoothStep(Math.min(attack, release));
    const contour = cueId === 'mhm' && progress > split ? 1.08 : 1;
    const wobble = 1 + Math.sin(progress * Math.PI * 2.1 + variant) * 0.012;
    const phase = Math.PI * 2 * base * contour * wobble * index / sampleRate;
    const nasal = Math.sin(phase) * 0.105
      + Math.sin(phase * 2.02 + 0.4) * 0.032
      + Math.sin(phase * 3.01 + 0.8) * 0.014;
    output[index] = nasal * envelope;
  }
  return output;
}

function createBreath(
  cueId: 'inhale' | 'amused_exhale',
  variant: number,
  sampleRate: number,
): Float32Array {
  const durationMs = cueId === 'inhale' ? 250 + variant * 24 : 330 + variant * 30;
  const length = Math.max(1, Math.round(sampleRate * durationMs / 1_000));
  const output = new Float32Array(length);
  const random = seededRandom((variant + 1) * (cueId === 'inhale' ? 7_919 : 10_007));
  let lowPassed = 0;
  let previous = 0;
  for (let index = 0; index < length; index += 1) {
    const progress = index / Math.max(1, length - 1);
    const raw = random() * 2 - 1;
    lowPassed += (raw - lowPassed) * (cueId === 'inhale' ? 0.22 : 0.14);
    const highPassed = lowPassed - previous * 0.82;
    previous = lowPassed;
    const shape = cueId === 'inhale'
      ? Math.sin(Math.PI * progress) ** 1.4
      : Math.sin(Math.PI * Math.min(1, progress * 1.08)) ** 1.15;
    const amusedPulse = cueId === 'amused_exhale'
      ? 0.78 + Math.sin(progress * Math.PI * 5 + variant) * 0.12
      : 1;
    output[index] = highPassed * shape * amusedPulse * (cueId === 'inhale' ? 0.085 : 0.075);
  }
  return output;
}

function parseVariant(variantId: string): number {
  const match = /-v(\d+)$/i.exec(variantId);
  const parsed = match ? Number(match[1]) - 1 : 0;
  return Math.max(0, Math.min(VARIANT_COUNT - 1, Number.isFinite(parsed) ? parsed : 0));
}

function smoothStep(value: number): number {
  const bounded = Math.max(0, Math.min(1, value));
  return bounded * bounded * (3 - 2 * bounded);
}

function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1_664_525 + 1_013_904_223) >>> 0;
    return state / 0x1_0000_0000;
  };
}
