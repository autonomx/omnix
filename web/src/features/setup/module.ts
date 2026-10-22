import { defineModule } from '../../app/moduleManifest';

/**
 * The desktop app's setup screen (desktop roadmap §4.5): what this machine can run, the licences, and downloading the
 * runtime packs and models. Reached from the first start and from Settings; not in the sidebar.
 */
export const setupModule = defineModule({
  id: 'setup',
  label: 'Set up Omnix',
  summary: 'Choose and download the AI models this computer can run.',
  route: '/setup',
  icon: '⇩',
  backendModules: [],
  usesOperations: [
    'GET /api/model-packs',
    'POST /api/model-packs/selection',
    'GET /api/model-packs/capabilities',
    'POST /api/model-packs/install',
    'POST /api/model-packs/remove',
    'POST /api/model-packs/verify',
    'GET /api/voice/models',
    'PUT /api/voice/models/hub-token',
    'GET /api/character-live2d/models',
    'POST /api/character-live2d/models/{model_id}',
    'DELETE /api/character-live2d/models/{model_id}',
  ],
  apiPrefixes: ['/api/model-packs', '/api/voice/models', '/api/jobs', '/api/settings', '/api/character-live2d'],
  sidebar: false,
  platform: true,
  loadWorkspace: () => import('./SetupWorkspace').then((module) => module.SetupWorkspace),
});
