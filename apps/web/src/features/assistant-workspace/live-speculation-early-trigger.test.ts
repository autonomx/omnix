import { describe, expect, it } from 'vitest';

import {
  earlySpeculationCandidateEligible,
  earlySpeculationProbabilityFloor,
} from './live-speculation-early-trigger';

describe('early live speculation trigger', () => {
  it('starts longer stable candidates at a lower bounded endpoint score', () => {
    expect(earlySpeculationProbabilityFloor('What kind of nonsense is this')).toBe(0.35);
    expect(earlySpeculationCandidateEligible(
      0.35,
      'What kind of nonsense is this',
    )).toBe(true);
  });

  it('requires more confidence for two-word candidates', () => {
    expect(earlySpeculationProbabilityFloor('Stop now')).toBe(0.6);
    expect(earlySpeculationCandidateEligible(0.59, 'Stop now')).toBe(false);
    expect(earlySpeculationCandidateEligible(0.6, 'Stop now')).toBe(true);
  });

  it('does not speculate from one-word fragments', () => {
    expect(earlySpeculationProbabilityFloor('What')).toBeNull();
    expect(earlySpeculationCandidateEligible(0.95, 'What')).toBe(false);
  });

  it('does not speculate below the bounded long-candidate probability floor', () => {
    expect(earlySpeculationCandidateEligible(
      0.34,
      'What kind of nonsense is this',
    )).toBe(false);
  });
});
