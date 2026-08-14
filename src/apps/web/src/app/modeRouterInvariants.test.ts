import { expect, test } from 'vitest';
import { readModeClientState } from './modeClient';
import { createOmnixModePreview } from './omnixModePreview';
import { getOmnixModeRoute, usesExistingOmnixPath } from './omnixModeRouter';
import { readModePlanStub } from './modePlanStub';

test('normal and live keep existing paths', () => {
  expect(usesExistingOmnixPath('normal')).toBe(true);
  expect(usesExistingOmnixPath('live')).toBe(true);
  expect(readModeClientState('normal').preview.path).toBe('direct');
  expect(readModeClientState('live').preview.path).toBe('live');
});

test('rpg stays simulation owned', () => {
  const route = getOmnixModeRoute('rpg');
  const preview = createOmnixModePreview('rpg');

  expect(route.path).toBe('sim');
  expect(route.owner).toBe('rpg_sim');
  expect(preview.status).toBe('ready');
});

test('review lanes do not appear as existing paths', () => {
  expect(usesExistingOmnixPath('agent')).toBe(false);
  expect(usesExistingOmnixPath('house')).toBe(false);
  expect(usesExistingOmnixPath('podcast')).toBe(false);
  expect(readModePlanStub('agent').reviewRequired).toBe(true);
});
