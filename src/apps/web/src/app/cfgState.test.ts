import { expect, test } from 'vitest';
import { cfgLine } from './cfgLine';
import { cfgState } from './cfgState';

test('cfg false', () => {
  const state = cfgState();
  expect(state).toEqual({ active: false, ready: false, readOnly: true, passive: true });
  expect(cfgLine(state)).toBe('Waiting');
});

test('cfg true', () => {
  const state = cfgState(true, true);
  expect(state).toEqual({ active: true, ready: true, readOnly: true, passive: true });
  expect(cfgLine(state)).toBe('Ready');
});

test('cfg holds ready until active', () => {
  expect(cfgState(false, true).ready).toBe(false);
});
