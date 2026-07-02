import { describe, expect, it } from 'vitest';
import { rangeLen } from './rangeLen';

describe('rangeLen', () => {
  it('counts array values', () => {
    expect(rangeLen(null)).toBe(0);
    expect(rangeLen(['a', 'b'])).toBe(2);
  });
});
