import type { SettingsDocument } from './settingsDocumentTypes';

export function rpgPreferenceSnapshot(value: SettingsDocument['rpg']) {
  return JSON.parse(JSON.stringify(value)) as SettingsDocument['rpg'];
}
