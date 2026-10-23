import { defineModule } from '../../app/moduleManifest';
// The assistant's events on the in-page bus (types only).
import './assistantEvents';

/** The workspace module this feature provides (WP-9.7). */
export const chatbotModule = defineModule({
  id: 'chatbot',
  label: 'Chatbot',
  summary: 'Text chat using the shared provider and model registry.',
  route: '/chatbot',
  icon: '▣',
  backendModules: ['agent-runtime', 'assistant-memory', 'assistant-tools', 'character-interactions', 'characters', 'chat', 'desktop-companion', 'live-voice', 'research'],
  apiPrefixes: [
    '/api/model-packs',
    '/api/chat', '/api/assistant', '/api/characters', '/api/character-avatar-generations',
    '/api/character-avatar-visemes', '/api/character-live2d', '/api/image-generation', '/api/live', '/api/live-chat',
    '/api/live-call', '/api/tts', '/api/voice', '/api/voice-profiles', '/api/voice-library', '/api/assets',
    '/api/jobs', '/api/providers', '/api/settings', '/api/hermes', '/api/agent', '/api/agent-runs', '/api/prompts',
    '/api/desktop-companion',
    // Live voice's speech service, through the gateway's proxy (authority probe, live socket, batch fallback).
    '/api/stt',
  ],
  modeLabel: 'Chat',
  loadWorkspace: () => import('./chat/ChatbotWorkspace').then((module) => module.ChatbotWorkspace),
  activateRuntime: async (context, store) => (await import('./runtime')).activateAssistantRuntime(context, store),
});
