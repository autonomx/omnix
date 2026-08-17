import { expect, test } from 'vitest';
import { createRpgRailModeState } from './rpgRailModeState';

test('maps payload', () => {
  const value = createRpgRailModeState({ ok: true, mode: 'rpg', role: 'suggest', owner: 'rpg_sim' });
  expect(value?.mode).toBe('rpg');
  expect(value?.role).toBe('suggest');
  expect(value?.owner).toBe('rpg_sim');
});

test('returns empty for failed payload', () => {
  expect(createRpgRailModeState({ ok: false })).toBeUndefined();
});
