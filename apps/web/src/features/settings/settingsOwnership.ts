import type { SettingsCategoryId, SettingsPersistenceOwner, SettingScope } from './settingsTypes';

export type SettingsOwnershipRecord = {
  key: string;
  categoryId: SettingsCategoryId;
  scope: SettingScope;
  currentOwner: SettingsPersistenceOwner;
  targetOwner: SettingsPersistenceOwner;
  migration: 'retain' | 'centralize' | 'summarize' | 'exclude';
  source: string;
  notes?: string;
};

export const SETTINGS_OWNERSHIP_MAP: SettingsOwnershipRecord[] = [
  { key: 'global.providers', categoryId: 'ai-providers', scope: 'global', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: '/api/settings' },
  { key: 'global.models', categoryId: 'models-runtime', scope: 'global', currentOwner: 'module-state', targetOwner: 'settings-api', migration: 'centralize', source: 'Chatbot and module model selectors' },
  { key: 'global.routing', categoryId: 'models-runtime', scope: 'global', currentOwner: 'module-state', targetOwner: 'settings-api', migration: 'centralize', source: 'RPG prompt profile registry and module defaults' },
  { key: 'appearance', categoryId: 'appearance-accessibility', scope: 'local', currentOwner: 'browser-storage', targetOwner: 'browser-storage', migration: 'retain', source: 'assistant workspace preferences' },
  { key: 'assistant.defaults', categoryId: 'assistant-chat', scope: 'module', currentOwner: 'browser-storage', targetOwner: 'settings-api', migration: 'centralize', source: 'Chatbot assistant settings storage' },
  { key: 'assistant.session-overrides', categoryId: 'assistant-chat', scope: 'session', currentOwner: 'session-state', targetOwner: 'session-state', migration: 'exclude', source: 'Chat session provider/model/system prompt', notes: 'Central settings supply defaults only.' },
  { key: 'voice.defaults', categoryId: 'voice-audio', scope: 'module', currentOwner: 'module-state', targetOwner: 'settings-api', migration: 'centralize', source: 'Voice Studio output defaults' },
  { key: 'voice.job-overrides', categoryId: 'voice-audio', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'Voice synthesis and cloning job payloads' },
  { key: 'storyteller.defaults', categoryId: 'storyteller-podcast', scope: 'module', currentOwner: 'module-state', targetOwner: 'settings-api', migration: 'centralize', source: 'Storyteller workspace defaults' },
  { key: 'storyteller.reading', categoryId: 'storyteller-podcast', scope: 'local', currentOwner: 'browser-storage', targetOwner: 'browser-storage', migration: 'retain', source: 'storyReadSettings local storage' },
  { key: 'podcast.defaults', categoryId: 'storyteller-podcast', scope: 'module', currentOwner: 'module-state', targetOwner: 'settings-api', migration: 'centralize', source: 'Podcast workspace constants and state' },
  { key: 'podcast.job-overrides', categoryId: 'storyteller-podcast', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'Podcast generation payload' },
  { key: 'rpg.campaign-preferences', categoryId: 'rpg', scope: 'module', currentOwner: 'module-state', targetOwner: 'settings-api', migration: 'centralize', source: 'RPG campaign wizard initial values' },
  { key: 'rpg.session-state', categoryId: 'rpg', scope: 'session', currentOwner: 'session-state', targetOwner: 'session-state', migration: 'exclude', source: 'Persisted RPG campaign state', notes: 'Changing defaults must never mutate an existing campaign.' },
  { key: 'rpg.hermes', categoryId: 'rpg', scope: 'module', currentOwner: 'integration-api', targetOwner: 'integration-api', migration: 'summarize', source: 'Hermes RPG configuration APIs' },
  { key: 'image.defaults', categoryId: 'images-speech-input', scope: 'module', currentOwner: 'job-payload', targetOwner: 'settings-api', migration: 'centralize', source: 'Image Generation form defaults' },
  { key: 'image.job-overrides', categoryId: 'images-speech-input', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'Image generation job payload' },
  { key: 'stt.defaults', categoryId: 'images-speech-input', scope: 'module', currentOwner: 'job-payload', targetOwner: 'settings-api', migration: 'centralize', source: 'STT form defaults' },
  { key: 'stt.job-overrides', categoryId: 'images-speech-input', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'STT job payload' },
  { key: 'tools.governance', categoryId: 'tools-integrations', scope: 'global', currentOwner: 'integration-api', targetOwner: 'integration-api', migration: 'summarize', source: 'Assistant Tool configuration API' },
  { key: 'hermes.runtime', categoryId: 'tools-integrations', scope: 'environment', currentOwner: 'environment', targetOwner: 'environment', migration: 'summarize', source: 'Hermes environment configuration and status APIs' },
  { key: 'jobs.runtime', categoryId: 'jobs-assets-storage', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/jobs and event stream' },
  { key: 'assets.runtime', categoryId: 'jobs-assets-storage', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/assets' },
  { key: 'storage.environment', categoryId: 'jobs-assets-storage', scope: 'environment', currentOwner: 'environment', targetOwner: 'environment', migration: 'summarize', source: 'Configured resource and data paths' },
  { key: 'diagnostics.runtime', categoryId: 'diagnostics-developer', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/runtime/status, /api/diagnostics, workers, model residency' },
];

export type SettingsOwnershipIssue = { code: 'duplicate-key' | 'invalid-exclusion' | 'invalid-status-owner' | 'missing-source'; key: string };

export function validateSettingsOwnership(records: SettingsOwnershipRecord[] = SETTINGS_OWNERSHIP_MAP): SettingsOwnershipIssue[] {
  const issues: SettingsOwnershipIssue[] = [];
  const keys = new Set<string>();
  for (const record of records) {
    if (keys.has(record.key)) issues.push({ code: 'duplicate-key', key: record.key });
    keys.add(record.key);
    if (!record.source.trim()) issues.push({ code: 'missing-source', key: record.key });
    if ((record.scope === 'job' || record.scope === 'session') && record.migration !== 'exclude') {
      issues.push({ code: 'invalid-exclusion', key: record.key });
    }
    if (record.scope === 'status' && record.targetOwner !== 'runtime-api' && record.targetOwner !== 'integration-api') {
      issues.push({ code: 'invalid-status-owner', key: record.key });
    }
  }
  return issues;
}

export function ownershipForKey(key: string): SettingsOwnershipRecord | undefined {
  return SETTINGS_OWNERSHIP_MAP.find((record) => record.key === key);
}

export function ownershipByMigration(migration: SettingsOwnershipRecord['migration']): SettingsOwnershipRecord[] {
  return SETTINGS_OWNERSHIP_MAP.filter((record) => record.migration === migration);
}
