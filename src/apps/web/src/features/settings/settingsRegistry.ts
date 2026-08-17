import {
  SETTINGS_CATEGORY_IDS,
  type SettingDefinition,
  type SettingsCategoryDefinition,
  type SettingsRegistryValidationIssue,
} from './settingsTypes';

export const SETTINGS_CATEGORIES: SettingsCategoryDefinition[] = [
  { id: 'overview', label: 'Overview', description: 'Global defaults and whole-system health.', icon: 'grid', order: 0 },
  { id: 'appearance-accessibility', label: 'Appearance & Accessibility', description: 'Theme, density, motion, captions, and accessibility preferences.', icon: 'display', order: 10, searchAliases: ['theme', 'dark mode', 'captions'] },
  { id: 'ai-providers', label: 'AI Providers', description: 'Provider defaults, configuration summaries, and connection testing.', icon: 'providers', order: 20, searchAliases: ['llm', 'tts', 'stt', 'image provider'] },
  { id: 'models-runtime', label: 'Models & Runtime', description: 'Model discovery, routing, residency, and runtime policy.', icon: 'chip', order: 30, searchAliases: ['gpu', 'vram', 'routing'] },
  { id: 'assistant-chat', label: 'Assistant & Chat', description: 'Assistant personality, voice, live chat, web research, and session defaults.', icon: 'chat', order: 40, searchAliases: ['quick search', 'deep research', 'web provider', 'citations'] },
  { id: 'voice-audio', label: 'Voice & Audio', description: 'Speech synthesis, voice cloning, playback, and output tuning.', icon: 'waveform', order: 50, searchAliases: ['tts', 'voice cloning'] },
  { id: 'storyteller-podcast', label: 'Storyteller & Podcast', description: 'Writing, reading, podcast, and narration defaults.', icon: 'book', order: 60 },
  { id: 'rpg', label: 'RPG', description: 'Campaign defaults, systems, AI presentation, and Hermes assistance.', icon: 'dice', order: 70 },
  { id: 'images-speech-input', label: 'Images & Speech Input', description: 'Image generation and transcription defaults.', icon: 'image', order: 80, searchAliases: ['flux', 'stt', 'microphone'] },
  { id: 'tools-integrations', label: 'Tools & Integrations', description: 'Tool governance, connected accounts, and Hermes.', icon: 'puzzle', order: 90 },
  { id: 'jobs-assets-storage', label: 'Jobs, Assets & Storage', description: 'Operational defaults, retention, assets, and storage.', icon: 'database', order: 100 },
  { id: 'diagnostics-developer', label: 'Diagnostics & Developer', description: 'Runtime health, logs, testing, and developer diagnostics.', icon: 'code', order: 110 },
];

export const INITIAL_SETTINGS_REGISTRY: SettingDefinition[] = [
  {
    key: 'global.providers.llm',
    categoryId: 'ai-providers',
    sectionId: 'default-providers',
    label: 'Default LLM provider',
    kind: 'select',
    scope: 'global',
    persistenceOwner: 'settings-api',
    writable: true,
    appliesTo: 'new-sessions-and-jobs',
    searchAliases: ['chat provider', 'language model provider'],
  },
  {
    key: 'assistant.researchDefaultMode',
    categoryId: 'assistant-chat',
    sectionId: 'web-research',
    label: 'Default web research mode',
    kind: 'select',
    defaultValue: 'disabled',
    scope: 'module',
    persistenceOwner: 'settings-api',
    writable: true,
    appliesTo: 'new-sessions',
    searchAliases: ['disabled', 'quick search', 'deep research'],
  },
  {
    key: 'assistant.researchProvider',
    categoryId: 'assistant-chat',
    sectionId: 'web-research',
    label: 'Web search provider',
    kind: 'select',
    defaultValue: 'duckduckgo',
    scope: 'module',
    persistenceOwner: 'settings-api',
    writable: true,
    appliesTo: 'new-jobs',
    searchAliases: ['brave', 'tavily', 'duckduckgo', 'playwright', 'browser search'],
  },
  {
    key: 'assistant.researchBudgets',
    categoryId: 'assistant-chat',
    sectionId: 'web-research-advanced',
    label: 'Research budgets',
    kind: 'object',
    scope: 'module',
    persistenceOwner: 'settings-api',
    writable: true,
    appliesTo: 'new-jobs',
    searchAliases: ['queries', 'sources', 'extracts', 'steps'],
  },
  {
    key: 'assistant.researchRuntimeStatus',
    categoryId: 'assistant-chat',
    sectionId: 'web-research-status',
    label: 'Research runtime status',
    kind: 'status',
    scope: 'status',
    persistenceOwner: 'runtime-api',
    writable: false,
    availability: 'read-only',
    searchAliases: ['credentials', 'provider status', 'coverage'],
  },
  {
    key: 'appearance.mode',
    categoryId: 'appearance-accessibility',
    sectionId: 'appearance',
    label: 'Appearance',
    kind: 'select',
    defaultValue: 'system',
    scope: 'local',
    persistenceOwner: 'browser-storage',
    writable: true,
    appliesTo: 'immediately',
  },
  {
    key: 'appearance.theme',
    categoryId: 'appearance-accessibility',
    sectionId: 'appearance',
    label: 'Theme palette',
    kind: 'select',
    defaultValue: 'aurora',
    scope: 'local',
    persistenceOwner: 'browser-storage',
    writable: true,
    appliesTo: 'immediately',
    searchAliases: ['graphite', 'grey', 'green', 'evergreen', 'aurora'],
  },
  {
    key: 'runtime.gateway.status',
    categoryId: 'diagnostics-developer',
    sectionId: 'runtime-status',
    label: 'Gateway status',
    kind: 'status',
    scope: 'status',
    persistenceOwner: 'runtime-api',
    writable: false,
    availability: 'read-only',
  },
  {
    key: 'environment.workers.imageUrl',
    categoryId: 'diagnostics-developer',
    sectionId: 'worker-configuration',
    label: 'Image worker URL',
    kind: 'string',
    scope: 'environment',
    persistenceOwner: 'environment',
    writable: false,
    restartRequired: true,
    appliesTo: 'after-restart',
    availability: 'read-only',
  },
];

const SETTING_KEY_PATTERN = /^[a-z][a-zA-Z0-9]*(?:[.-][a-zA-Z0-9]+)+$/;

export function validateSettingsRegistry(
  categories: SettingsCategoryDefinition[] = SETTINGS_CATEGORIES,
  settings: SettingDefinition[] = INITIAL_SETTINGS_REGISTRY,
): SettingsRegistryValidationIssue[] {
  const issues: SettingsRegistryValidationIssue[] = [];
  const categoryIds = new Set<string>();

  for (const category of categories) {
    if (categoryIds.has(category.id)) {
      issues.push({ code: 'duplicate-category-id', key: category.id, message: `Duplicate settings category: ${category.id}` });
    }
    categoryIds.add(category.id);
  }

  const settingKeys = new Set<string>();
  for (const setting of settings) {
    if (settingKeys.has(setting.key)) {
      issues.push({ code: 'duplicate-setting-key', key: setting.key, message: `Duplicate setting key: ${setting.key}` });
    }
    settingKeys.add(setting.key);

    if (!SETTING_KEY_PATTERN.test(setting.key)) {
      issues.push({ code: 'invalid-setting-key', key: setting.key, message: `Invalid setting key: ${setting.key}` });
    }
    if (!categoryIds.has(setting.categoryId)) {
      issues.push({ code: 'unknown-category', key: setting.key, message: `Unknown category ${setting.categoryId} for ${setting.key}` });
    }
    if ((setting.scope === 'environment' || setting.scope === 'status') && setting.writable !== false) {
      issues.push({ code: 'writable-noneditable-scope', key: setting.key, message: `${setting.scope} setting ${setting.key} must be read-only` });
    }
    if (setting.scope === 'environment' && setting.persistenceOwner !== 'environment') {
      issues.push({ code: 'invalid-persistence-owner', key: setting.key, message: `Environment setting ${setting.key} must be owned by environment configuration` });
    }
    if (setting.scope === 'status' && setting.persistenceOwner !== 'runtime-api' && setting.persistenceOwner !== 'integration-api') {
      issues.push({ code: 'invalid-persistence-owner', key: setting.key, message: `Status setting ${setting.key} must be owned by a runtime or integration API` });
    }
  }

  return issues;
}

export function settingsByCategory(categoryId: SettingsCategoryDefinition['id'], settings = INITIAL_SETTINGS_REGISTRY): SettingDefinition[] {
  return settings.filter((setting) => setting.categoryId === categoryId);
}

export function sortedSettingsCategories(categories = SETTINGS_CATEGORIES): SettingsCategoryDefinition[] {
  return [...categories].sort((left, right) => left.order - right.order || left.label.localeCompare(right.label));
}

export function isSettingsCategoryId(value: string): value is SettingsCategoryDefinition['id'] {
  return (SETTINGS_CATEGORY_IDS as readonly string[]).includes(value);
}
