import { describe, expect, it } from 'vitest';

import {
  normalizeSpeculationWords,
  shouldStartExtendedHypothesis,
  transcriptExtendsSpeculation,
  transcriptsCanReuseSpeculation,
} from './live-speculation-controller';

describe('live speculation hypothesis policy', () => {
  it('keeps punctuation-insensitive exact final reuse strict at the word level', () => {
    expect(transcriptsCanReuseSpeculation(
      'What kind of nonsense',
      'What kind of nonsense?',
    )).toBe(true);
    expect(transcriptsCanReuseSpeculation(
      'What kind of',
      'What kind of nonsense?',
    )).toBe(false);
  });

  it('recognizes monotonic transcript extensions without treating them as corrections', () => {
    expect(transcriptExtendsSpeculation(
      'What kind of',
      'What kind of nonsense is that',
    )).toBe(true);
    expect(transcriptExtendsSpeculation(
      'What kind of',
      'What type of nonsense',
    )).toBe(false);
  });

  it('starts a replacement hypothesis after two new words', () => {
    expect(shouldStartExtendedHypothesis(
      'Tell me about',
      'Tell me about the weather',
      0.7,
    )).toBe(true);
    expect(shouldStartExtendedHypothesis(
      'Tell me about',
      'Tell me about weather',
      0.7,
    )).toBe(false);
  });

  it('allows one-word replacement only for a very strong endpoint candidate', () => {
    expect(shouldStartExtendedHypothesis(
      'Tell me about',
      'Tell me about weather',
      0.86,
    )).toBe(true);
  });

  it('normalizes curly apostrophes for final compatibility', () => {
    expect(normalizeSpeculationWords('That’s wild')).toEqual(["that's", 'wild']);
  });
});
