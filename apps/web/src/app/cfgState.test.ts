import { expect, test } from 'vitest';
import { cfgState } from './cfgState';

test('cfg false', () => {
  expect(cfgState()).toEqual({ active: false, ready: false, readOnly: true, passive: true });
});

test('cfg true', () => {
  expect(cfgState(true, true)).toEqual({ active: true, ready: true, readOnly: true, passive: true });
});

test('cfg holds ready until active', () => {
  expect(cfgState(false, true).ready).toBe(false);
});
