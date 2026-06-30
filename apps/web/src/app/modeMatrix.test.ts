import { expect, test } from 'vitest';
import { readModeClientState } from './modeClient';
import { createOmnixModePreview } from './omnixModePreview';
import { getModeRouteStatusInfo } from './modeRouteStatus';
import { usesExistingOmnixPath } from './omnixModeRouter';
import { makeTaskContract } from './taskContract';

test('mode matrix stays stable', () => {
  expect(readModeClientState('normal').preview.path).toBe('direct');
  expect(readModeClientState('live').preview.path).toBe('live');
  expect(createOmnixModePreview('rpg').owner).toBe('rpg_sim');
  expect(getModeRouteStatusInfo('adapter').tone).toBe('review');
  expect(makeTaskContract('agent', 'x').review).toBe(true);
  expect(usesExistingOmnixPath('normal')).toBe(true);
  expect(usesExistingOmnixPath('agent')).toBe(false);
});
