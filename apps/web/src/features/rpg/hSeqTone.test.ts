import { describe, expect, it } from 'vitest';
import { hSeqHasRows, hSeqItemCount } from './hSeqTone';

describe('hSeq item count', () => {
  it('counts rows', () => {
    expect(hSeqItemCount(null)).toBe(0);
    expect(hSeqItemCount({ items: [{ statement: 'inspect room' }, { statement: 'listen' }] })).toBe(2);
  });

  it('reports whether rows exist', () => {
    expect(hSeqHasRows({ items: [] })).toBe(false);
    expect(hSeqHasRows({ items: [{ statement: 'inspect room' }] })).toBe(true);
  });
});
