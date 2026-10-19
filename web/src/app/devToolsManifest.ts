import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

/**
 * Development-only pages, served outside the workstation shell. Production builds
 * see an empty list, so the pages and their data are not bundled.
 */
export const devToolPages: Array<{ path: string; component: LazyExoticComponent<ComponentType> }> = import.meta.env.DEV
  ? [
    // Chat generative UI: every golden fixture per theme, appearance and width (GUI-2.5).
    { path: '/dev/chat-ui-fixtures', component: lazy(() => import('../features/assistant/chat/generative-ui/ChatUiFixtureGallery')) },
  ]
  : [];
