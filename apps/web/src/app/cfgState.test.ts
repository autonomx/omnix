import { expect, test } from 'vitest';
import { cfgState } from './cfgState';

test('cfg false', () => {
  expect(cfgState()).toEqual({ active: false });
});

test('cfg true', () => {
  expect(cfgState(true)).toEqual({ active: true });
});
