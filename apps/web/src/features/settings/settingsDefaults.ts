import { SETTINGS_SCHEMA_VERSION, type SettingsDocument } from './settingsDocumentTypes';

export const DEFAULT_SETTINGS_DOCUMENT: SettingsDocument = {
  schemaVersion: SETTINGS_SCHEMA_VERSION,
  revision: 'default',
  global: {
    providers: { llm: 'lmstudio', tts: 'faster-qwen3-tts', stt: 'parakeet', image: '', voiceCloning: '' },
    models: { chat: '', fast: '', quality: '', background: '', embedding: '', imagePrompt: '' },
    routing: { fallbackBehavior: 'next-available', taskOverrides: {} },
  },
  appearance: { mode: 'system', density: 'comfortable', reduceMotion: false, liveCaptions: true },
  assistant: { personalityId: 'omnix-default', customPersonality: '', voiceId: '', autoSpeakReplies: false, speechLanguage: 'en-US', streamingAudio: true },
  voice: { language: 'English', stability: 0.75, similarity: 0.8, style: 0.35, speed: 1, pitch: 0, volume: 0, effects: [], streaming: true, cloningLanguage: 'English', cloningQuality: 'High' },
  storyteller: { providerId: '', modelId: '', tone: 'Cozy', writingStyle: 'Lyrical & Descriptive', readSpeed: 1, pauseParagraphMs: 500, pauseChapterMs: 1200, readChapterTitles: true, readStylePreset: 'Dramatic audiobook', pronunciation: {} },
  podcast: { providerId: '', modelId: '', format: 'interview', durationMinutes: 5, tone: 'Professional', language: 'English (US)', generationStyle: 'automatic', autoplay: false, playbackRate: 1, stability: 0.72, similarity: 0.78, effects: ['Compression', 'De-esser'] },
  rpg: { difficulty: 'normal', worldActivity: 'standard', economyPressure: 'normal', combatLethality: 'normal', companions: true, permadeath: false, autosave: true, validator: true, backgroundSoftAudit: true, llmNarration: true, imageGeneration: false, tts: false, stt: false, campaignDefaults: {}, hermesAssistMode: 'review_each_step' },
  image: { width: 768, height: 768, aspectRatio: '1:1', portraitPreset: '', scenePreset: '', unloadAfterGeneration: true },
  stt: { language: '', alignment: true, saveTranscript: true, microphoneDeviceId: '', noiseSuppression: true, echoCancellation: true },
  storage: { saveOutputByDefault: true, retentionDays: 30, temporaryAssetCleanup: true },
};
