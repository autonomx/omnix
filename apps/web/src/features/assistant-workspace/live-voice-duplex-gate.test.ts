import { describe, expect, it } from 'vitest';

import { resolveDuplexMode, shouldMuteLiveMic } from './live-voice-duplex-gate';

describe('live voice duplex gate', () => {
  it('keeps automatic mode on the safe half-duplex fallback', () => {
    expect(resolveDuplexMode('automatic')).toBe('half_duplex');
    expect(shouldMuteLiveMic(true, 'half_duplex')).toBe(true);
    expect(shouldMuteLiveMic(false, 'half_duplex')).toBe(false);
  });

  it('keeps microphone capture enabled in explicit echo-aware mode', () => {
    expect(resolveDuplexMode('echo_aware', true)).toBe('echo_aware');
    expect(shouldMuteLiveMic(true, 'echo_aware')).toBe(false);
  });

  it('falls back safely when echo-aware support is unavailable', () => {
    expect(resolveDuplexMode('echo_aware', false)).toBe('half_duplex');
    expect(resolveDuplexMode('half_duplex')).toBe('half_duplex');
  });
});
