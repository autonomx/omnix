import { migrateSettingsDocument, settingsPatch } from './settingsMerge';
import type { SettingsDocument } from './settingsDocumentTypes';

export type SettingsApiPayload = {
  success: boolean;
  provider: string;
  audio_provider_tts: string;
  audio_provider_stt: string;
  settings?: Record<string, unknown>;
};

export type SettingsProfileEnvelope = {
  profile: SettingsDocument;
  legacy: SettingsApiPayload;
};

export type SettingsProfileSaveRequest = {
  base_revision: string;
  settings_profile_patch: Partial<SettingsDocument>;
};

export class SettingsProfileApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export type SettingsFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export async function loadSettingsProfile(fetcher: SettingsFetch = fetch): Promise<SettingsProfileEnvelope> {
  const response = await fetcher('/api/settings');
  if (!response.ok) throw new SettingsProfileApiError('Settings request failed.', response.status);
  const legacy = await response.json() as SettingsApiPayload;
  const raw = legacy.settings?.settings_control_center;
  return { profile: migrateSettingsDocument(raw), legacy };
}

export async function saveSettingsProfile(request: SettingsProfileSaveRequest, fetcher: SettingsFetch = fetch): Promise<void> {
  const response = await fetcher('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new SettingsProfileApiError('Settings save failed.', response.status);
  const result = await response.json() as { success?: boolean };
  if (result.success !== true) throw new SettingsProfileApiError('Settings were not saved because the profile changed or validation failed.', 409);
}

export function createSettingsSaveRequest(base: SettingsDocument, draft: SettingsDocument): SettingsProfileSaveRequest {
  return { base_revision: base.revision, settings_profile_patch: settingsPatch(base, draft) };
}
