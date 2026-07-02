import { describe, expect, it } from 'vitest';
import { rangeHas } from './rangeHas';

describe('rangeHas', () => {
  it('works', () => {
    expect(rangeHas(null)).toBe(false);
    expect(rangeHas([])).toBe(false);
    expect(rangeHas(['x'])).toBe(true);
  });
});
