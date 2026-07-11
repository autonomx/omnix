import { describe, expect, it } from 'vitest';

import {
  BoundedWaveformReference,
  compareRecentWaveforms,
  pcm16ToFloat32Reference,
  resampleWaveform,
} from './live-voice-waveform-reference';

function tone(length: number, period = 24): Float32Array {
  return Float32Array.from({ length }, (_, index) => Math.sin(2 * Math.PI * index / period) * 0.4);
}

function deterministicNoise(length: number, seed: number): Float32Array {
  let state = seed >>> 0;
  return Float32Array.from({ length }, () => {
    state = (Math.imul(state, 1_664_525) + 1_013_904_223) >>> 0;
    return (state / 0xffff_ffff * 2 - 1) * 0.35;
  });
}

describe('live voice waveform reference', () => {
  it('keeps only the bounded newest playback samples', () => {
    const reference = new BoundedWaveformReference(256);
    reference.append(Float32Array.from({ length: 200 }, (_, index) => index));
    reference.append(Float32Array.from({ length: 100 }, (_, index) => index + 200));

    const snapshot = reference.snapshot();
    expect(snapshot).toHaveLength(256);
    expect(snapshot[0]).toBe(44);
    expect(snapshot.at(-1)).toBe(299);
  });

  it('finds a delayed playback waveform and rejects unrelated speech', () => {
    const playback = deterministicNoise(2_400, 17);
    const echoed = playback.slice(1_700, 2_200);
    const unrelated = deterministicNoise(500, 91_337);

    const match = compareRecentWaveforms(playback, echoed, 24_000, 300);
    const mismatch = compareRecentWaveforms(playback, unrelated, 24_000, 300);

    expect(match.similarity).not.toBeNull();
    expect(match.similarity ?? 0).toBeGreaterThan(0.99);
    expect(mismatch.similarity ?? 1).toBeLessThan(0.25);
    expect(match.comparedSamples).toBeGreaterThan(100);
  });

  it('normalizes PCM and resamples microphone frames to playback rate', () => {
    expect(Array.from(pcm16ToFloat32Reference(new Int16Array([0, 16384, -32768]))))
      .toEqual([0, 0.5, -1]);
    const resampled = resampleWaveform(tone(480), 48_000, 24_000);
    expect(resampled).toHaveLength(240);
  });
});
