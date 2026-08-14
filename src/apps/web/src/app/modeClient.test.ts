import { expect, test } from 'vitest';
import { readModeClientState } from './modeClient';

test('returns metadata for a valid mode', () => {
  const state = readModeClientState('rpg');

  expect(state.ok).toBe(true);
  expect(state.fallback).toBe(false);
  expect(state.preview.path).toBe('sim');
});

test('returns fallback metadata for an invalid mode', () => {
  const state = readModeClientState('bad');

  expect(state.ok).toBe(true);
  expect(state.fallback).toBe(true);
  expect(state.preview.mode).toBe('normal');
});
