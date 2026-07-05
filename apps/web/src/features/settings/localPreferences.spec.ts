import { describe, expect, it } from 'vitest';
import { SETTINGS_LOCAL_STORAGE_KEY, loadSettingsLocalPreferences, type SettingsStorage } from './settingsLocalPreferences';

function memoryStorage(seed: Record<string, string> = {}): SettingsStorage {
  const values = new Map(Object.entries(seed));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
  };
}

describe('local settings preferences', () => {
  it('migrates assistant and story reader values once', () => {
    const storage = memoryStorage({
      'omnix.chatbot.assistantSettings': JSON.stringify({ voiceId: 'voice-1', personalityId: 'technical', customPersonality: '' }),
      'omnix.storyteller.readSettings': JSON.stringify({ speed: 1.2, pauseAfterParagraphMs: 750, stylePreset: 'Calm' }),
    });
    const preferences = loadSettingsLocalPreferences(storage);
    expect(preferences.assistant.voiceId).toBe('voice-1');
    expect(preferences.storyRead.readSpeed).toBe(1.2);
    expect(storage.getItem(SETTINGS_LOCAL_STORAGE_KEY)).toBeTruthy();
  });

  it('falls back safely when stored JSON is malformed', () => {
    const preferences = loadSettingsLocalPreferences(memoryStorage({ [SETTINGS_LOCAL_STORAGE_KEY]: '{bad' }));
    expect(preferences.appearance.mode).toBe('system');
  });
});
