import { describe, expect, it } from 'vitest';

import { earlySpeculationCandidateEligible } from './live-speculation-early-trigger';

describe('early live speculation trigger', () => {
  it('starts private work at a moderate Kyutai endpoint score', () => {
    expect(earlySpeculationCandidateEligible(
      0.5,
      'What kind of nonsense',
    )).toBe(true);
  });

  it('does not speculate from one-word fragments', () => {
    expect(earlySpeculationCandidateEligible(0.95, 'What')).toBe(false);
  });

  it('does not speculate below the bounded probability floor', () => {
    expect(earlySpeculationCandidateEligible(
      0.49,
      'What kind of nonsense',
    )).toBe(false);
  });
});
