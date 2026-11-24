import { defineModule } from '../../app/moduleManifest';

/** The workspace module this feature provides (WP-9.7). */
export const podcastModule = defineModule({
  id: 'podcast',
  label: 'Podcast',
  summary: 'Script planning, multi-speaker synthesis, mixing, and podcast exports.',
  route: '/podcast',
  icon: '◉',
  backendModules: [],
  apiPrefixes: [
    '/api/assets', '/api/jobs', '/api/providers', '/api/settings', '/api/tts', '/api/voice', '/api/agent',
    '/api/prompts',
    // Its voices: every clone in the voice library, as the chat lists them.
    '/api/voice-library',
    // Its cast: library characters and their avatar packs (D4).
    '/api/characters',
    // Its research: one web search on the topic, as source notes (story's route).
    '/api/podcast',
  ],
  usesOperations: ['POST /api/podcast/research'],
  modeLabel: 'Podcast',
  loadWorkspace: () => import('./PodcastWorkspace').then((module) => module.PodcastWorkspace),
});
