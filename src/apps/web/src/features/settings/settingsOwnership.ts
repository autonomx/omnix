import type { SettingsCategoryId, SettingsPersistenceOwner, SettingScope } from './settingsTypes';

export type SettingsOwnershipRecord = {
  key: string;
  categoryId: SettingsCategoryId;
  scope: SettingScope;
  currentOwner: SettingsPersistenceOwner;
  targetOwner: SettingsPersistenceOwner;
  migration: 'retain' | 'centralize' | 'summarize' | 'exclude';
  source: string;
  runtimeConsumer?: string;
  notes?: string;
};

export const SETTINGS_OWNERSHIP_MAP: SettingsOwnershipRecord[] = [
  { key: 'global.providers', categoryId: 'ai-providers', scope: 'global', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: '/api/settings', runtimeConsumer: 'app.platform.effective_defaults.effective_llm_route' },
  { key: 'global.models', categoryId: 'models-runtime', scope: 'global', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: '/api/settings settings profile', runtimeConsumer: 'effectiveTaskRoute / effective_llm_route' },
  { key: 'global.routing', categoryId: 'models-runtime', scope: 'global', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: '/api/settings settings profile', runtimeConsumer: 'effectiveTaskRoute / effective_llm_route' },
  { key: 'appearance', categoryId: 'appearance-accessibility', scope: 'local', currentOwner: 'browser-storage', targetOwner: 'browser-storage', migration: 'retain', source: 'assistant workspace preferences' },
  { key: 'assistant.defaults', categoryId: 'assistant-chat', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center assistant profile', runtimeConsumer: 'CreateChatSessionRequest.apply_central_defaults' },
  { key: 'assistant.session-overrides', categoryId: 'assistant-chat', scope: 'session', currentOwner: 'session-state', targetOwner: 'session-state', migration: 'exclude', source: 'Chat session provider/model/system prompt', notes: 'Central settings supply defaults only.' },
  { key: 'assistant.research.defaults', categoryId: 'assistant-chat', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center assistant profile', runtimeConsumer: 'assistant research runtime settings', notes: 'The retired browser mirror is no longer read or written.' },
  { key: 'assistant.research.conversation-override', categoryId: 'assistant-chat', scope: 'session', currentOwner: 'session-state', targetOwner: 'session-state', migration: 'exclude', source: 'Chat session research_mode_override', notes: 'Persisted only by the backend chat-session contract.' },
  { key: 'assistant.research.runtime', categoryId: 'assistant-chat', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/assistant/research/status' },
  { key: 'assistant.research.credentials', categoryId: 'assistant-chat', scope: 'environment', currentOwner: 'environment', targetOwner: 'environment', migration: 'summarize', source: 'OMNIX_WEB_SEARCH_API_KEY and provider integration secrets', notes: 'Never browser-readable.' },
  { key: 'voice.defaults', categoryId: 'voice-audio', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center voice profile', runtimeConsumer: 'voiceStudioDefaults / _apply_voice_defaults' },
  { key: 'voice.job-overrides', categoryId: 'voice-audio', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'Voice synthesis and cloning job payloads' },
  { key: 'storyteller.defaults', categoryId: 'storyteller-podcast', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center storyteller profile', runtimeConsumer: 'storytellerDefaults / _apply_storyteller_defaults' },
  { key: 'storyteller.reading', categoryId: 'storyteller-podcast', scope: 'local', currentOwner: 'browser-storage', targetOwner: 'browser-storage', migration: 'retain', source: 'storyReadSettings local storage' },
  { key: 'podcast.defaults', categoryId: 'storyteller-podcast', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center podcast profile', runtimeConsumer: 'podcastDefaults / podcastSessionGuard / _apply_podcast_defaults' },
  { key: 'podcast.job-overrides', categoryId: 'storyteller-podcast', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'Podcast generation payload' },
  { key: 'rpg.campaign-preferences', categoryId: 'rpg', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center RPG profile', runtimeConsumer: 'rpgWizardDefaultsFromSettings' },
  { key: 'rpg.session-state', categoryId: 'rpg', scope: 'session', currentOwner: 'session-state', targetOwner: 'session-state', migration: 'exclude', source: 'Persisted RPG campaign state', notes: 'Changing defaults must never mutate an existing campaign.' },
  { key: 'rpg.hermes', categoryId: 'rpg', scope: 'module', currentOwner: 'integration-api', targetOwner: 'integration-api', migration: 'summarize', source: 'Hermes RPG configuration APIs' },
  { key: 'image.defaults', categoryId: 'images-speech-input', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center image profile', runtimeConsumer: 'imageGenerationDefaults / _apply_image_defaults' },
  { key: 'image.job-overrides', categoryId: 'images-speech-input', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'Image generation job payload' },
  { key: 'stt.defaults', categoryId: 'images-speech-input', scope: 'module', currentOwner: 'settings-api', targetOwner: 'settings-api', migration: 'retain', source: 'Settings Control Center STT profile', runtimeConsumer: 'speechInputDefaults / _apply_stt_defaults' },
  { key: 'stt.job-overrides', categoryId: 'images-speech-input', scope: 'job', currentOwner: 'job-payload', targetOwner: 'job-payload', migration: 'exclude', source: 'STT job payload' },
  { key: 'tools.governance', categoryId: 'tools-integrations', scope: 'global', currentOwner: 'integration-api', targetOwner: 'integration-api', migration: 'summarize', source: 'Assistant Tool configuration API' },
  { key: 'hermes.runtime', categoryId: 'tools-integrations', scope: 'environment', currentOwner: 'environment', targetOwner: 'environment', migration: 'summarize', source: 'Hermes environment configuration and status APIs' },
  { key: 'jobs.runtime', categoryId: 'jobs-assets-storage', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/jobs and event stream' },
  { key: 'assets.runtime', categoryId: 'jobs-assets-storage', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/assets' },
  { key: 'storage.environment', categoryId: 'jobs-assets-storage', scope: 'environment', currentOwner: 'environment', targetOwner: 'environment', migration: 'summarize', source: 'Configured resource and data paths' },
  { key: 'diagnostics.runtime', categoryId: 'diagnostics-developer', scope: 'status', currentOwner: 'runtime-api', targetOwner: 'runtime-api', migration: 'summarize', source: '/api/runtime/status, /api/diagnostics, workers, model residency' },
];

export type SettingsOwnershipIssue = { code: 'duplicate-key' | 'invalid-exclusion' | 'invalid-status-owner' | 'missing-source' | 'missing-runtime-consumer'; key: string };

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
    if (record.targetOwner === 'settings-api' && record.migration !== 'exclude' && !record.runtimeConsumer?.trim()) {
      issues.push({ code: 'missing-runtime-consumer', key: record.key });
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
