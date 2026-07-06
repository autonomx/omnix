import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS_DOCUMENT } from './settingsDefaults';
import { imageGenerationDefaults, rpgCampaignDefaults, speechInputDefaults, voiceStudioDefaults } from './moduleDefaults';

describe('module default adapters', () => {
  it('maps central image and speech preferences', () => {
    const document = {
      ...DEFAULT_SETTINGS_DOCUMENT,
      image: { ...DEFAULT_SETTINGS_DOCUMENT.image, width: 1024 },
      stt: { ...DEFAULT_SETTINGS_DOCUMENT.stt, language: 'en' },
    };
    expect(imageGenerationDefaults(document).width).toBe(1024);
    expect(imageGenerationDefaults(document).providerId).toBe('image:flux_klein');
    expect(speechInputDefaults(document).language).toBe('en');
  });

  it('uses flux as the image provider when older profiles have no image default', () => {
    const document = {
      ...DEFAULT_SETTINGS_DOCUMENT,
      global: {
        ...DEFAULT_SETTINGS_DOCUMENT.global,
        providers: { ...DEFAULT_SETTINGS_DOCUMENT.global.providers, image: '' },
      },
    };
    expect(imageGenerationDefaults(document).providerId).toBe('image:flux_klein');
  });

  it('maps voice values and isolates RPG defaults', () => {
    expect(voiceStudioDefaults(DEFAULT_SETTINGS_DOCUMENT).speed).toBe(1);
    const campaign = rpgCampaignDefaults(DEFAULT_SETTINGS_DOCUMENT);
    campaign.difficulty = 'harsh';
    expect(DEFAULT_SETTINGS_DOCUMENT.rpg.difficulty).toBe('normal');
  });
});
