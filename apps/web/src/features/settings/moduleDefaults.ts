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
