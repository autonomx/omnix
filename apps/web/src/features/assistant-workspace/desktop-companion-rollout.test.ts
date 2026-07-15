import { describe, expect, it } from 'vitest';

import { DEFAULT_SETTINGS_DOCUMENT } from '../settings/settingsDefaults';
import { effectiveDesktopCompanionSettings } from './desktop-companion-rollout';


describe('desktop companion rollout settings', () => {
  it('keeps the runtime disabled even if a stage is selected without the enable switch', () => {
    const settings = {
      ...DEFAULT_SETTINGS_DOCUMENT.assistant,
      desktopCompanionEnabled: false,
      desktopCompanionRolloutStage: 'speech' as const,
      autoSpeakReplies: true,
    };

    expect(effectiveDesktopCompanionSettings(settings)).toMatchObject({
      requestedStage: 'disabled',
      enabled: false,
      shadowMode: false,
      textEnabled: false,
      speechEnabled: false,
    });
  });

  it('requires auto-speak before the effective speech setting becomes active', () => {
    const base = {
      ...DEFAULT_SETTINGS_DOCUMENT.assistant,
      desktopCompanionEnabled: true,
      desktopCompanionRolloutStage: 'speech' as const,
    };

    expect(effectiveDesktopCompanionSettings({ ...base, autoSpeakReplies: false }).speechEnabled).toBe(false);
    expect(effectiveDesktopCompanionSettings({ ...base, autoSpeakReplies: true }).speechEnabled).toBe(true);
  });
});
