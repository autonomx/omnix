import { afterEach, describe, expect, it } from 'vitest';
import { liveConversationStore } from './live-conversation-store';
import {
  DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG,
  createAssistantWorkspaceRuntimeConfig,
} from './runtime-config';

afterEach(() => {
  document.body.innerHTML = '';
  liveConversationStore.reset();
  window.dispatchEvent(new CustomEvent('omnix:character-avatar-runtime', { detail: null }));
});

describe('createAssistantWorkspaceRuntimeConfig', () => {
  it('uses durable defaults when env values are absent', () => {
    expect(createAssistantWorkspaceRuntimeConfig({})).toEqual(DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG);
  });

  it('reads workspace services and feature flags while leaving provider defaults server-owned', () => {
    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_WORKSPACE_ID: 'workspace:lab',
      VITE_ASSISTANT_PROJECT_ID: 'project:omnix',
      VITE_ASSISTANT_PROVIDER_ID: 'lmstudio',
      VITE_ASSISTANT_MODEL_ID: 'qwen-local',
      VITE_ASSISTANT_STT_URL: 'http://localhost:5201/transcribe',
      VITE_ASSISTANT_TTS_URL: 'http://localhost:5101/synthesize',
      VITE_ASSISTANT_TTS_VOICE: 'narrator',
      VITE_ASSISTANT_EVENT_STORAGE_KEY: 'omnix.test.events',
      VITE_ASSISTANT_LIVE_ENABLED: 'true',
      VITE_ASSISTANT_PERSISTED_EVENTS: 'false',
      VITE_ASSISTANT_TOOL_EXECUTION: '1',
    });

    expect(config).toMatchObject({
      workspaceId: 'workspace:lab',
      projectId: 'project:omnix',
      defaultProviderId: undefined,
      defaultModelId: undefined,
      sttServiceUrl: 'http://localhost:5201/transcribe',
      ttsServiceUrl: 'http://localhost:5101/synthesize',
      ttsVoice: 'narrator',
      eventStorageKey: 'omnix.test.events',
      features: {
        liveAssistant: true,
        persistedEvents: false,
        toolExecution: true,
      },
    });
  });

  it('uses the active Character Mode speaker instead of the static default voice', () => {
    document.body.innerHTML = '<section class="assistant-live-card" data-live-voice-id="Inigo"></section>';

    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_TTS_VOICE: 'default',
    });

    expect(config.ttsVoice).toBe('Inigo');
  });

  it('uses the session-scoped Character Mode store when the rendered voice is temporarily empty', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-id="">
        <span class="assistant-live-identity active">Talking to Jinx</span>
      </section>`;
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:jinx' });
    liveConversationStore.dispatch({
      type: 'identity',
      identity: {
        characterId: 'jinx',
        displayName: 'Jinx',
        voiceId: 'Jinx',
        profileVersion: 4,
      },
    });

    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_TTS_VOICE: 'default',
    });

    expect(config.ttsVoice).toBe('Jinx');
  });

  it('uses the exact server-published speaker when store identity has not populated yet', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-id="">
        <span class="assistant-live-identity active">Talking to Jinx</span>
      </section>`;
    window.dispatchEvent(new CustomEvent('omnix:character-avatar-runtime', {
      detail: {
        session_id: 'chat:jinx',
        interaction_mode: 'character',
        character_id: 'jinx',
        display_name: 'Jinx',
        voice_asset_id: 'voice-cloning:jinx',
        voice_speaker_id: 'Jinx',
      },
    }));

    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_TTS_VOICE: 'default',
    });

    expect(config.ttsVoice).toBe('Jinx');
  });

  it('does not use a published speaker belonging to a different active character', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-id="">
        <span class="assistant-live-identity active">Talking to Maya</span>
      </section>`;
    window.dispatchEvent(new CustomEvent('omnix:character-avatar-runtime', {
      detail: {
        session_id: 'chat:jinx',
        interaction_mode: 'character',
        character_id: 'jinx',
        display_name: 'Jinx',
        voice_speaker_id: 'Jinx',
      },
    }));

    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_TTS_VOICE: 'default',
    });

    expect(config.ttsVoice).toBe('default');
  });

  it('does not leak a stale character-store voice into a System Assistant session', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-id="">
        <span class="assistant-live-identity">System Assistant</span>
      </section>`;
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:old-character' });
    liveConversationStore.dispatch({
      type: 'identity',
      identity: {
        characterId: 'jinx',
        displayName: 'Jinx',
        voiceId: 'Jinx',
        profileVersion: 4,
      },
    });

    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_TTS_VOICE: 'default',
    });

    expect(config.ttsVoice).toBe('default');
  });

  it('ignores empty strings and unknown boolean values', () => {
    const config = createAssistantWorkspaceRuntimeConfig({
      VITE_ASSISTANT_WORKSPACE_ID: '   ',
      VITE_ASSISTANT_PROVIDER_ID: '',
      VITE_ASSISTANT_LIVE_ENABLED: 'maybe',
    });

    expect(config.workspaceId).toBe(DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.workspaceId);
    expect(config.defaultProviderId).toBeUndefined();
    expect(config.features.liveAssistant).toBe(DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG.features.liveAssistant);
  });
});
