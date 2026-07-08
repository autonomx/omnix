// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { migrateSettingsDocument } from './settingsMerge';
import {
  commitAppearanceSettings,
  loadStoredAppearancePreferences,
  OMNIX_APPEARANCE_CHANGE_EVENT,
  OMNIX_APPEARANCE_MODE_STORAGE_KEY,
  OMNIX_THEME_STORAGE_KEY,
} from './appearanceEffects';

describe('appearance theme effects', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-omnix-appearance');
    document.documentElement.removeAttribute('data-omnix-appearance-preference');
    document.documentElement.removeAttribute('data-omnix-theme');
    document.documentElement.removeAttribute('data-omnix-density');
    document.documentElement.classList.remove('omnix-reduce-motion');
  });

  it('applies, persists, and announces a selected theme', () => {
    const listener = vi.fn();
    window.addEventListener(OMNIX_APPEARANCE_CHANGE_EVENT, listener);

    const detail = commitAppearanceSettings({
      mode: 'light',
      theme: 'graphite',
      density: 'compact',
      reduceMotion: true,
    });

    expect(detail).toEqual({ mode: 'light', resolvedMode: 'light', theme: 'graphite' });
    expect(document.documentElement.dataset.omnixAppearance).toBe('light');
    expect(document.documentElement.dataset.omnixTheme).toBe('graphite');
    expect(document.documentElement.dataset.omnixDensity).toBe('compact');
    expect(document.documentElement.classList.contains('omnix-reduce-motion')).toBe(true);
    expect(window.localStorage.getItem(OMNIX_APPEARANCE_MODE_STORAGE_KEY)).toBe('light');
    expect(window.localStorage.getItem(OMNIX_THEME_STORAGE_KEY)).toBe('graphite');
    expect(listener).toHaveBeenCalledTimes(1);

    window.removeEventListener(OMNIX_APPEARANCE_CHANGE_EVENT, listener);
  });

  it('loads stored mode and theme preferences', () => {
    window.localStorage.setItem(OMNIX_APPEARANCE_MODE_STORAGE_KEY, 'dark');
    window.localStorage.setItem(OMNIX_THEME_STORAGE_KEY, 'evergreen');

    expect(loadStoredAppearancePreferences()).toEqual({ mode: 'dark', theme: 'evergreen' });
  });

  it('falls back to Aurora when an older profile has no theme', () => {
    const migrated = migrateSettingsDocument({ appearance: { mode: 'light' } });

    expect(migrated.appearance.mode).toBe('light');
    expect(migrated.appearance.theme).toBe('aurora');
  });
});
