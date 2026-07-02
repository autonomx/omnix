import { describe, expect, it } from 'vitest';
import { rangeFirst } from './rangeFirst';

describe('rangeFirst', () => {
  it('returns the first item', () => {
    expect(rangeFirst(null)).toBeUndefined();
    expect(rangeFirst(['a', 'b'])).toBe('a');
  });
});
