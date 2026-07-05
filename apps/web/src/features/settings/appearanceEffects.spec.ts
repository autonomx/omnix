import { describe, expect, it } from 'vitest';
import { applyAppearanceSettings } from './appearanceEffects';

describe('appearance effects', () => {
  it('applies theme, density, and reduced motion markers', () => {
    applyAppearanceSettings({ mode: 'dark', density: 'compact', reduceMotion: true });
    expect(document.documentElement.dataset.omnixAppearance).toBe('dark');
    expect(document.documentElement.dataset.omnixDensity).toBe('compact');
    expect(document.documentElement.classList.contains('omnix-reduce-motion')).toBe(true);
  });
});
