import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG,
  createAssistantWorkspaceRuntimeConfig,
} from './runtime-config';

describe('createAssistantWorkspaceRuntimeConfig', () => {
  it('uses durable defaults when env values are absent', () => {
    expect(createAssistantWorkspaceRuntimeConfig({})).toEqual(DEFAULT_ASSISTANT_WORKSPACE_RUNTIME_CONFIG);
  });

  it('reads workspace services, defaults, and feature flags from Vite env values', () => {
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
      defaultProviderId: 'lmstudio',
      defaultModelId: 'qwen-local',
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
