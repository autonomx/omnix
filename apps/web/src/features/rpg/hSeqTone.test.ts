import { describe, expect, it } from 'vitest';
import { hSeqHasGate, hSeqTone } from './hSeqTone';

describe('hSeqTone', () => {
  it('maps levels to tones', () => {
    expect(hSeqTone({ risk: 'low' })).toBe('quiet');
    expect(hSeqTone({ risk: 'medium' })).toBe('warn');
    expect(hSeqTone({ risk: 'high' })).toBe('danger');
  });

  it('detects gated rows', () => {
    expect(hSeqHasGate(null)).toBe(false);
    expect(hSeqHasGate({ items: [{ user_gate: false }] })).toBe(false);
    expect(hSeqHasGate({ items: [{ user_gate: true }] })).toBe(true);
  });
});
