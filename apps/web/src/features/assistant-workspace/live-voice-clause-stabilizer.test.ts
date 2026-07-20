import { describe, expect, it } from 'vitest';

import { StableClauseAccumulator, mergeStreamText } from './live-voice-clause-stabilizer';

describe('stable live voice clauses', () => {
  it('commits strong terminal punctuation incrementally', () => {
    const accumulator = new StableClauseAccumulator({ minimumClauseCharacters: 12 });

    expect(accumulator.append('This is the first complete thought.', 0)).toEqual([
      { text: 'This is the first complete thought.', reason: 'strong-boundary' },
    ]);
    expect(accumulator.pendingText()).toBe('');
  });

  it('uses lookahead before committing weaker punctuation', () => {
    const accumulator = new StableClauseAccumulator({
      minimumClauseCharacters: 12,
      stableLookaheadCharacters: 12,
    });

    expect(accumulator.append('There are two options,', 0)).toEqual([]);
    expect(accumulator.append('and the safer one keeps state isolated.', 50)).toEqual([
      { text: 'There are two options,', reason: 'stable-boundary' },
      { text: 'and the safer one keeps state isolated.', reason: 'strong-boundary' },
    ]);
  });

  it('does not split decimals, abbreviations, URLs, or unclosed parentheses', () => {
    const accumulator = new StableClauseAccumulator({
      minimumClauseCharacters: 8,
      maximumClauseCharacters: 200,
    });

    expect(accumulator.append('Use version 2.5 and ask Dr. Smith to check (the URL https://example.com/a.b', 0)).toEqual([]);
    expect(accumulator.append('after the call).', 50)).toEqual([
      {
        text: 'Use version 2.5 and ask Dr. Smith to check (the URL https://example.com/a.b after the call).',
        reason: 'strong-boundary',
      },
    ]);
  });

  it('commits a safe fallback when the latency deadline expires', () => {
    const accumulator = new StableClauseAccumulator({
      minimumClauseCharacters: 12,
      deadlineMs: 100,
    });

    expect(accumulator.append('This answer has enough words for a safe deadline split', 0)).toEqual([]);
    expect(accumulator.takeReady(101)).toEqual([
      { text: 'This answer has enough words for a safe deadline', reason: 'deadline' },
    ]);
    expect(accumulator.pendingText()).toBe('split');
  });

  it('flushes the unspoken tail only at stream end', () => {
    const accumulator = new StableClauseAccumulator();
    accumulator.append('A final short tail', 0);
    expect(accumulator.flush()).toEqual([{ text: 'A final short tail', reason: 'stream-end' }]);
    expect(accumulator.flush()).toEqual([]);
  });

  it('merges punctuation chunks without introducing spoken spacing artifacts', () => {
    expect(mergeStreamText('Hello', '.')).toBe('Hello.');
    expect(mergeStreamText('Use', '(carefully')).toBe('Use (carefully');
  });
});
