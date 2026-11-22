import { createSettingsSaveRequest, loadSettingsProfile, saveSettingsProfile } from './settingsApi';
import type { AssistantSettings } from './settingsDocumentTypes';

/**
 * Saves a change to the assistant's settings from outside the Settings page, which keeps a draft of its own: the
 * profile is read as saved now, so the change is made on the latest revision and leaves every other setting as it is.
 */
export async function saveAssistantSettings(change: Partial<AssistantSettings>): Promise<AssistantSettings> {
  const { profile } = await loadSettingsProfile();
  const next = { ...profile, assistant: { ...profile.assistant, ...change } };
  await saveSettingsProfile(createSettingsSaveRequest(profile, next));
  return next.assistant;
}
