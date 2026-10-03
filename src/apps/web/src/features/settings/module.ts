import { defineModule } from '../../app/moduleManifest';

/** The workspace module this feature provides (WP-9.7). */
export const settingsModule = defineModule({
  id: 'settings',
  label: 'Settings',
  summary: 'Global app, provider, model, local service, and feature settings.',
  route: '/settings',
  icon: '⚙',
  apiPrefixes: [
    '/api/settings', '/api/providers', '/api/models', '/api/runtime', '/api/assistant', '/api/hermes',
    '/api/diagnostics', '/api/workers', '/api/trading/market-data',
  ],
  platform: true,
  loadWorkspace: () => import('./SettingsWorkspace').then((module) => module.SettingsWorkspace),
});
