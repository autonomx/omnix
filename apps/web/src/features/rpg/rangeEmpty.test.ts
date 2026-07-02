import { describe, expect, it } from 'vitest';
import { rangeEmpty } from './rangeEmpty';

describe('rangeEmpty', () => {
  it('checks empty arrays', () => {
    expect(rangeEmpty(null)).toBe(true);
    expect(rangeEmpty([])).toBe(true);
    expect(rangeEmpty(['x'])).toBe(false);
  });
});
