export type AssistantWorkspaceRuntimeFeatureFlags = {
  liveAssistant: boolean;
  persistedEvents: boolean;
  toolExecution: boolean;
};

export type AssistantWorkspaceRuntimeConfig = {
  workspaceId: string;
  projectId?: string;
  defaultProviderId?: string;
  defaultModelId?: string;
  sttServiceUrl?: string;
  ttsServiceUrl?: string;
  ttsVoice?: string;
  eventStorageKey: string;
  features: AssistantWorkspaceRuntimeFeatureFlags;
};

export type AssistantWorkspaceRuntimeEnv = Record<string, string | boolean | number | undefined>;

export const DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG: AssistantWorkspaceRuntimeConfig = {
  workspaceId: 'workspace:default',
  projectId: 'project:chatbot',
  eventStorageKey: 'omnix.assistantWorkspace.events',
  features: {
    liveAssistant: true,
    persistedEvents: true,
    toolExecution: true,
  },
};

export function createAssistantWorkspaceRuntimeConfig(
  env: AssistantWorkspaceRuntimeEnv = getImportMetaEnv(),
): AssistantWorkspaceRuntimeConfig {
  return {
    workspaceId: readString(env, 'VITE_ASSISTANT_WORKSPACE_ID') ?? DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.workspaceId,
    projectId: readString(env, 'VITE_ASSISTANT_PROJECT_ID') ?? DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.projectId,
    // Provider and model defaults are authoritative in the Settings Control Center.
    // Leaving these unset lets new sessions resolve PostgreSQL-backed defaults while
    // explicit selectors and existing session overrides continue to win.
    defaultProviderId: undefined,
    defaultModelId: undefined,
    sttServiceUrl: readString(env, 'VITE_ASSISTANT_STT_URL'),
    ttsServiceUrl: readString(env, 'VITE_ASSISTANT_TTS_URL'),
    // Character Mode is authoritative while its Live Voice card is mounted. Legacy
    // response-audio paths call this factory at playback time, so resolving the card
    // here prevents them from silently falling back to the static configured voice.
    ttsVoice: readActiveCharacterVoice() ?? readString(env, 'VITE_ASSISTANT_TTS_VOICE'),
    eventStorageKey:
      readString(env, 'VITE_ASSISTANT_EVENT_STORAGE_KEY') ??
      DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.eventStorageKey,
    features: {
      liveAssistant:
        readBoolean(env, 'VITE_ASSISTANT_LIVE_ENABLED') ??
        DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.features.liveAssistant,
      persistedEvents:
        readBoolean(env, 'VITE_ASSISTANT_PERSISTED_EVENTS') ??
        DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.features.persistedEvents,
      toolExecution:
        readBoolean(env, 'VITE_ASSISTANT_TOOL_EXECUTION') ??
        DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.features.toolExecution,
    },
  };
}

function getImportMetaEnv(): AssistantWorkspaceRuntimeEnv {
  return ((import.meta as unknown as { env?: AssistantWorkspaceRuntimeEnv }).env ?? {}) as AssistantWorkspaceRuntimeEnv;
}

function readActiveCharacterVoice(): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const activeVoice = document
    .querySelector<HTMLElement>('.assistant-live-card')
    ?.dataset.liveVoiceId
    ?.trim();
  return activeVoice || undefined;
}

function readString(env: AssistantWorkspaceRuntimeEnv, key: string): string | undefined {
  const value = env[key];
  if (value === undefined || value === false) return undefined;
  const text = String(value).trim();
  return text ? text : undefined;
}

function readBoolean(env: AssistantWorkspaceRuntimeEnv, key: string): boolean | undefined {
  const value = env[key];
  if (value === undefined) return undefined;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on', 'enabled'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'disabled'].includes(normalized)) return false;
  return undefined;
}
