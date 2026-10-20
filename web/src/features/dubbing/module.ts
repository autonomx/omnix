import { defineModule } from '../../app/moduleManifest';

/** The workspace module this feature provides (scaffolded, PA-4.2). */
export const dubbingModule = defineModule({
  id: 'dubbing',
  label: 'Dubbing',
  summary: 'Translate and re-voice a video, approving every line.',
  route: '/dubbing',
  icon: '⇄',
  backendModules: ['dubbing'],
  apiPrefixes: ['/api/dubbing'],
  loadWorkspace: () => import('./DubbingWorkspace').then((module) => module.DubbingWorkspace),
});
