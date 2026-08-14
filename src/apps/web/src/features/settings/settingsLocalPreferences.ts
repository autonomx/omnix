import { DEFAULT_SETTINGS_DOCUMENT } from './settingsDefaults';

export const SETTINGS_LOCAL_STORAGE_KEY = 'omnix.settings.local.v1';
const LEGACY_ASSISTANT_KEY = 'omnix.chatbot.assistantSettings';
const LEGACY_STORY_READ_KEY = 'omnix.storyteller.readSettings';

export type SettingsStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export type SettingsLocalPreferences = {
  appearance: typeof DEFAULT_SETTINGS_DOCUMENT.appearance;
  assistant: Pick<typeof DEFAULT_SETTINGS_DOCUMENT.assistant, 'voiceId' | 'personalityId' | 'customPersonality'>;
  storyRead: Pick<typeof DEFAULT_SETTINGS_DOCUMENT.storyteller, 'readSpeed' | 'pauseParagraphMs' | 'pauseChapterMs' | 'readChapterTitles' | 'readStylePreset'> & { pronunciationDictionary: string };
};

export const DEFAULT_LOCAL_PREFERENCES: SettingsLocalPreferences = {
  appearance: { ...DEFAULT_SETTINGS_DOCUMENT.appearance },
  assistant: {
    voiceId: DEFAULT_SETTINGS_DOCUMENT.assistant.voiceId,
    personalityId: DEFAULT_SETTINGS_DOCUMENT.assistant.personalityId,
    customPersonality: DEFAULT_SETTINGS_DOCUMENT.assistant.customPersonality,
  },
  storyRead: {
    readSpeed: DEFAULT_SETTINGS_DOCUMENT.storyteller.readSpeed,
    pauseParagraphMs: DEFAULT_SETTINGS_DOCUMENT.storyteller.pauseParagraphMs,
    pauseChapterMs: DEFAULT_SETTINGS_DOCUMENT.storyteller.pauseChapterMs,
    readChapterTitles: DEFAULT_SETTINGS_DOCUMENT.storyteller.readChapterTitles,
    readStylePreset: DEFAULT_SETTINGS_DOCUMENT.storyteller.readStylePreset,
    pronunciationDictionary: '',
  },
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function parse(storage: SettingsStorage, key: string): Record<string, unknown> {
  try { return record(JSON.parse(storage.getItem(key) || '{}')); } catch { return {}; }
}

export function loadSettingsLocalPreferences(storage: SettingsStorage): SettingsLocalPreferences {
  const current = parse(storage, SETTINGS_LOCAL_STORAGE_KEY);
  if (Object.keys(current).length) return mergeLocalPreferences(current);

  const assistant = parse(storage, LEGACY_ASSISTANT_KEY);
  const story = parse(storage, LEGACY_STORY_READ_KEY);
  const migrated = mergeLocalPreferences({
    assistant: {
      voiceId: assistant.voiceId,
      personalityId: assistant.personalityId,
      customPersonality: assistant.customPersonality,
    },
    storyRead: {
      readSpeed: story.speed,
      pauseParagraphMs: story.pauseAfterParagraphMs,
      pauseChapterMs: story.pauseAfterChapterMs,
      readChapterTitles: story.readChapterTitles,
      readStylePreset: story.stylePreset,
      pronunciationDictionary: story.pronunciationDictionary,
    },
  });
  saveSettingsLocalPreferences(storage, migrated);
  return migrated;
}

export function saveSettingsLocalPreferences(storage: SettingsStorage, preferences: SettingsLocalPreferences): void {
  storage.setItem(SETTINGS_LOCAL_STORAGE_KEY, JSON.stringify(preferences));
}

export function mergeLocalPreferences(value: unknown): SettingsLocalPreferences {
  const source = record(value);
  const appearance = record(source.appearance);
  const assistant = record(source.assistant);
  const story = record(source.storyRead);
  return {
    appearance: { ...DEFAULT_LOCAL_PREFERENCES.appearance, ...appearance } as SettingsLocalPreferences['appearance'],
    assistant: {
      voiceId: typeof assistant.voiceId === 'string' ? assistant.voiceId : DEFAULT_LOCAL_PREFERENCES.assistant.voiceId,
      personalityId: typeof assistant.personalityId === 'string' ? assistant.personalityId : DEFAULT_LOCAL_PREFERENCES.assistant.personalityId,
      customPersonality: typeof assistant.customPersonality === 'string' ? assistant.customPersonality : DEFAULT_LOCAL_PREFERENCES.assistant.customPersonality,
    },
    storyRead: { ...DEFAULT_LOCAL_PREFERENCES.storyRead, ...story } as SettingsLocalPreferences['storyRead'],
  };
}
