import { liveConversationStore } from './live-conversation-store';

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

type PublishedCharacterRuntime = {
  sessionId: string;
  characterId: string;
  displayName: string;
  speakerId: string;
};

type CharacterRuntimeEventDetail = {
  session_id?: unknown;
  interaction_mode?: unknown;
  character_id?: unknown;
  display_name?: unknown;
  voice_speaker_id?: unknown;
  voice_asset_id?: unknown;
};

let publishedCharacterRuntime: PublishedCharacterRuntime | null = null;

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

installCharacterRuntimeVoiceBridge();

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

function installCharacterRuntimeVoiceBridge(): void {
  if (typeof window === 'undefined') return;
  window.addEventListener('omnix:character-avatar-runtime', (event) => {
    const detail = (event as CustomEvent<CharacterRuntimeEventDetail | null>).detail;
    if (!detail || detail.interaction_mode !== 'character') {
      publishedCharacterRuntime = null;
      return;
    }
    const sessionId = textValue(detail.session_id);
    const characterId = textValue(detail.character_id);
    const displayName = textValue(detail.display_name);
    const speakerId = textValue(detail.voice_speaker_id)
      || textValue(detail.voice_asset_id).replace(/^voice-cloning:/, '');
    publishedCharacterRuntime = sessionId && characterId && displayName && speakerId
      ? { sessionId, characterId, displayName, speakerId }
      : null;
  });
}

function readActiveCharacterVoice(): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const card = document.querySelector<HTMLElement>('.assistant-live-card');
  const renderedVoice = card?.dataset.liveVoiceId?.trim();
  if (renderedVoice) return renderedVoice;

  const activeIdentity = card?.querySelector<HTMLElement>('.assistant-live-identity.active');
  if (!activeIdentity) return undefined;

  // React can intentionally retain the current live-call runtime object while a call
  // is connected. The session-scoped conversation store is updated immediately by
  // the trusted runtime/voice-assignment event bridge, so use it when available.
  const storeState = liveConversationStore.getState();
  const storedVoice = storeState.identity.characterId !== 'system-assistant'
    ? storeState.identity.voiceId?.trim()
    : '';
  if (storedVoice) return storedVoice;

  // Ordinary runtime loads publish the trusted server runtime through the avatar
  // bridge even when the conversation store has not yet received identity state.
  // Match the visible active identity before using the cached speaker so a runtime
  // from a prior character or session cannot leak into the current conversation.
  const published = publishedCharacterRuntime;
  const visibleIdentity = normalizeIdentity(activeIdentity.textContent ?? '');
  if (published && visibleIdentity.includes(normalizeIdentity(published.displayName))) {
    return published.speakerId;
  }
  return undefined;
}

function normalizeIdentity(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/^talking to\s+/, '');
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
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
