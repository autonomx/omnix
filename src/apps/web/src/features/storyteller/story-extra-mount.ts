import * as React from 'react';
import { createRoot } from 'react-dom/client';
import { StoryExtraPanels } from './StoryExtraPanels';

function mount(): void {
  const host = document.getElementById('omnix-story-audio-panel-root') ?? document.querySelector('.storyteller-project-header');
  if (!host || document.getElementById('omnix-story-extra-root')) return;
  const node = document.createElement('div');
  node.id = 'omnix-story-extra-root';
  host.insertAdjacentElement('afterend', node);
  createRoot(node).render(React.createElement(StoryExtraPanels));
}

if (typeof window !== 'undefined') {
  window.setTimeout(mount, 0);
  window.setTimeout(mount, 500);
  window.addEventListener('focus', mount);
}
