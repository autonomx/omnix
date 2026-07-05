import { expect, it } from 'vitest';
import { DEFAULT_SETTINGS_DOCUMENT } from './settingsDefaults';
import { rpgPreferenceSnapshot } from './rpgPreferenceSeed';

it('clones campaign preferences', () => {
  const snapshot = rpgPreferenceSnapshot(DEFAULT_SETTINGS_DOCUMENT.rpg);
  snapshot.difficulty = 'harsh';
  expect(DEFAULT_SETTINGS_DOCUMENT.rpg.difficulty).toBe('normal');
});
