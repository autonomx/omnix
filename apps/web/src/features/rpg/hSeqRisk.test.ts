import { describe, expect, it } from 'vitest';
import { hSeqNeedsReview, hSeqRiskTone } from './hSeqRisk';

describe('hSeqRisk', () => {
  it('maps values to tones', () => {
    expect(hSeqRiskTone({ risk: 'low' })).toBe('quiet');
    expect(hSeqRiskTone({ risk: 'medium' })).toBe('warn');
    expect(hSeqRiskTone({ risk: 'high' })).toBe('danger');
  });

  it('detects gated rows', () => {
    expect(hSeqNeedsReview(null)).toBe(false);
    expect(hSeqNeedsReview({ items: [{ user_gate: false }] })).toBe(false);
    expect(hSeqNeedsReview({ items: [{ user_gate: true }] })).toBe(true);
  });
});
