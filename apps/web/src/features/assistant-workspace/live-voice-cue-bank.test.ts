import { describe, expect, it } from 'vitest';

import {
  clearCueSampleCache,
  cloneCueSamples,
  cueVariantCount,
  cueVariantId,
  getCachedCueSamples,
} from './live-voice-cue-bank';

describe('live voice cue bank', () => {
  it('caches stable variants without sharing transferable clones', () => {
    clearCueSampleCache();
    const cached = getCachedCueSamples('hmm', 'hmm-v1', 24_000);
    expect(getCachedCueSamples('hmm', 'hmm-v1', 24_000)).toBe(cached);
    const clone = cloneCueSamples('hmm', 'hmm-v1', 24_000);
    expect(clone).not.toBe(cached);
    expect(Array.from(clone)).toEqual(Array.from(cached));
  });

  it('produces multiple bounded non-identical variants for every initial cue', () => {
    expect(cueVariantCount()).toBe(4);
    for (const cue of ['mhm', 'hmm', 'inhale', 'amused_exhale'] as const) {
      const first = getCachedCueSamples(cue, cueVariantId(cue, 0), 24_000);
      const second = getCachedCueSamples(cue, cueVariantId(cue, 1), 24_000);
      expect(first.length).toBeGreaterThan(2_000);
      expect(second.length).not.toBe(first.length);
      expect(Math.max(...first)).toBeLessThan(0.2);
      expect(Math.min(...first)).toBeGreaterThan(-0.2);
    }
  });

  it('generates cue duration in the requested playback sample domain', () => {
    const at24k = getCachedCueSamples('inhale', 'inhale-v1', 24_000);
    const at48k = getCachedCueSamples('inhale', 'inhale-v1', 48_000);
    expect(at48k.length).toBe(at24k.length * 2);
  });
});
