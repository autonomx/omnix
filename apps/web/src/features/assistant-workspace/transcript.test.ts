import { describe, expect, it } from 'vitest';
import { createTranscriptSegment, getFinalTranscriptText, replacePartialTranscript } from './transcript';

describe('transcript contracts', () => {
  it('joins final transcript text', () => {
    expect(getFinalTranscriptText([
      { id: 'a', text: ' hello ', status: 'final', createdAt: 't1' },
      { id: 'b', text: 'there', status: 'partial', createdAt: 't2' },
    ])).toBe('hello');
  });

  it('replaces partial transcript segments', () => {
    const partial = createTranscriptSegment({ id: 'p2', text: 'next', status: 'partial', createdAt: 't2' });
    expect(replacePartialTranscript([{ id: 'p1', text: 'old', status: 'partial', createdAt: 't1' }], partial)).toEqual([partial]);
  });
});
