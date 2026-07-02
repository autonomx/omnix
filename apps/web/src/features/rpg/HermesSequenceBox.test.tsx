import { describe, expect, it } from 'vitest';
import { hSeqSummary } from './hSeqSummary';

describe('hSeqSummary', () => {
  it('summarizes preview state', () => {
    expect(hSeqSummary(null)).toBe('not ready');
    expect(hSeqSummary({ objective: 'Room details', items: [{ statement: 'inspect room' }] })).toBe('Room details (1 item)');
  });
});
