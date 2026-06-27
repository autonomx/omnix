import * as React from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { StoryAudioPanel } from './StoryAudioPanel';
import { StoryCastPanel } from './StoryCastPanel';
import { StoryChapterAudioPanel } from './StoryChapterAudioPanel';
import { StoryDocumentPanel } from './StoryDocumentPanel';
import { StoryVoiceCastPanel } from './StoryVoiceCastPanel';

const STORY_AUDIO_MOUNT_ID = 'omnix-story-audio-panel-root';

let mountedRoot: Root | null = null;
let mountedElement: HTMLElement | null = null;
let observerStarted = false;
let renderScheduled = false;

function StorytellerAudioAndCast() {
  return React.createElement(
    'details',
    { className: 'storyteller-toolbox storyteller-toolbox-primary' },
    React.createElement(
      'summary',
      null,
      React.createElement('span', null, React.createElement('strong', null, 'Audio & cast tools'), React.createElement('small', null, 'Narration, voices, character registry, chapter audio, structured JSON')), 
      React.createElement('em', null, 'Open tools'),
    ),
    React.createElement(
      'div',
      { className: 'storyteller-toolbox-content storyteller-toolbox-grid' },
      React.createElement(StoryAudioPanel, { key: 'audio' }),
      React.createElement(StoryVoiceCastPanel, { key: 'voice-cast' }),
      React.createElement(StoryCastPanel, { key: 'cast' }),
      React.createElement(StoryChapterAudioPanel, { key: 'chapter-audio' }),
      React.createElement(StoryDocumentPanel, { key: 'document' }),
    ),
  );
}

function scheduleStoryAudioMount(): void {
  if (renderScheduled) return;
  renderScheduled = true;
  window.requestAnimationFrame(() => {
    renderScheduled = false;
    mountStoryAudioPanel();
  });
}

function mountStoryAudioPanel(): void {
  const header = document.querySelector('.storyteller-project-header');
  if (!header) return;

  let mountElement = document.getElementById(STORY_AUDIO_MOUNT_ID);
  if (!mountElement) {
    mountElement = document.createElement('div');
    mountElement.id = STORY_AUDIO_MOUNT_ID;
    header.insertAdjacentElement('afterend', mountElement);
  }

  if (mountedElement === mountElement && mountedRoot) return;
  mountedRoot?.unmount();
  mountedElement = mountElement;
  mountedRoot = createRoot(mountElement);
  mountedRoot.render(React.createElement(StorytellerAudioAndCast));
}

function installStoryAudioEnhancer(): void {
  if (observerStarted || typeof window === 'undefined' || typeof document === 'undefined') return;
  observerStarted = true;
  scheduleStoryAudioMount();
  const observer = new MutationObserver((mutations) => {
    if (mutations.every((mutation) => {
      const target = mutation.target as Node;
      return mountedElement ? mountedElement.contains(target) : false;
    })) return;
    scheduleStoryAudioMount();
  });
  observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('popstate', scheduleStoryAudioMount);
  window.addEventListener('hashchange', scheduleStoryAudioMount);
}

installStoryAudioEnhancer();
