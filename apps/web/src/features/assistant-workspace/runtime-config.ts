import { readLatestTrustedCharacterRuntime } from '../chatbot/characterClient';
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
    // Character Mode is authoritative while its trusted runtime belongs to the
    // currently selected session. Legacy response-audio paths call this factory at
    // playback time, so they receive the exact case-sensitive TTS speaker.
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
  const card = document.querySelector<HTMLElement>('.assistant-live-card');
  const renderedVoice = card?.dataset.liveVoiceId?.trim();
  if (renderedVoice) return renderedVoice;

  const renderedIdentity = normalizeIdentity(
    card?.querySelector<HTMLElement>('.assistant-live-identity')?.textContent ?? '',
  );
  if (renderedIdentity === 'system assistant') return undefined;

  const storeState = liveConversationStore.getState();
  const storeCharacterActive = storeState.identity.characterId !== 'system-assistant';
  const storedVoice = storeCharacterActive ? storeState.identity.voiceId?.trim() : '';
  const activeIdentity = card?.querySelector<HTMLElement>('.assistant-live-identity.active');
  const visibleIdentity = normalizeIdentity(activeIdentity?.textContent ?? '');

  // characterClient retains the normalized result of every successful trusted
  // /live-call/runtime request. Reading it directly avoids losing the speaker when
  // the avatar event fired before this module loaded or before React rendered the
  // data-live-voice-id attribute.
  const runtime = readLatestTrustedCharacterRuntime();
  if (runtime?.interaction_mode === 'character') {
    const speakerId = runtime.voice_speaker_id?.trim() || runtime.voice_asset_id?.trim();
    const sameSelectedSession = Boolean(
      storeCharacterActive
      && storeState.sessionId
      && storeState.sessionId === runtime.session_id,
    );
    const sameVisibleCharacter = Boolean(
      visibleIdentity
      && visibleIdentity.includes(normalizeIdentity(runtime.display_name)),
    );
    if ((sameSelectedSession || sameVisibleCharacter) && (storedVoice || speakerId)) {
      return storedVoice || speakerId;
    }
  }

  // A hot-swapped assignment updates the session-scoped identity before the runtime
  // refresh can finish. Permit that exact voice only when the visible active identity
  // still matches the store's character.
  const storedDisplayName = normalizeIdentity(storeState.identity.displayName);
  if (storedVoice && visibleIdentity && storedDisplayName && visibleIdentity.includes(storedDisplayName)) {
    return storedVoice;
  }
  return undefined;
}

function normalizeIdentity(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/^talking to\s+/, '');
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
