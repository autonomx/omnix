import { expect, test } from 'vitest';
import { createModeState } from './modeState';

test('keeps a valid mode value', () => {
  expect(createModeState('rpg')).toEqual({ id: 'rpg', label: 'RPG', fallback: false });
});

test('uses fallback for an invalid value', () => {
  expect(createModeState('bad')).toEqual({ id: 'normal', label: 'Normal chat', fallback: true });
});
