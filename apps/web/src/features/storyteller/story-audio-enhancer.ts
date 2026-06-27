import * as React from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { StoryAudioPanel } from './StoryAudioPanel';
import { StoryCastPanel } from './StoryCastPanel';

const STORY_AUDIO_MOUNT_ID = 'omnix-story-audio-panel-root';

let mountedRoot: Root | null = null;
let mountedElement: HTMLElement | null = null;
let observerStarted = false;
let renderScheduled = false;

function StorytellerAudioAndCast() {
  return React.createElement(React.Fragment, null, [
    React.createElement(StoryAudioPanel, { key: 'audio' }),
    React.createElement(StoryCastPanel, { key: 'cast' }),
  ]);
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
