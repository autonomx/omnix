import { DEFAULT_SETTINGS_DOCUMENT } from './settingsDefaults';
import type { SettingsDocument } from './settingsDocumentTypes';

export function imageGenerationDefaults(document: SettingsDocument = DEFAULT_SETTINGS_DOCUMENT) {
  return {
    providerId: document.global.providers.image,
    width: document.image.width,
    height: document.image.height,
    unloadAfterGeneration: document.image.unloadAfterGeneration,
  };
}

export function speechInputDefaults(document: SettingsDocument = DEFAULT_SETTINGS_DOCUMENT) {
  return {
    providerId: document.global.providers.stt,
    language: document.stt.language,
    alignment: document.stt.alignment,
    saveTranscript: document.stt.saveTranscript,
  };
}

export function voiceStudioDefaults(document: SettingsDocument = DEFAULT_SETTINGS_DOCUMENT) {
  return {
    providerId: document.global.providers.tts,
    stability: document.voice.stability,
    similarity: document.voice.similarity,
    style: document.voice.style,
    speed: document.voice.speed,
    pitch: document.voice.pitch,
    volume: document.voice.volume,
    effects: [...document.voice.effects],
    cloningLanguage: document.voice.cloningLanguage,
    cloningQuality: document.voice.cloningQuality,
  };
}
